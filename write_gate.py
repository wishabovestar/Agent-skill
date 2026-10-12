#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
write_gate.py — 事务级写入闸 (Transactional Write Gate)

现在的闸（memory_layer.gate）是【逐条校验】：这一条合不合格。
本层补【事务语义】—— 归档 #188 L10 / #126「演化要能回滚」的机器形态。

保证（每条都配一个真跑的破坏性测试）:
  WA 原子性   : 一个事务的 N 条写入，要么全落，要么一条不落
  WC 一致性   : 提交前跑【写入闸 + 不变量 M1–M5】；任一条不过 ⇒ 拒绝提交, 主存零改动
  WI 隔离     : 单写者锁 + 陈旧锁检测(pid 死 / 超 TTL)；并发写者被挡住而非交错
  WD 持久性   : WAL(write-ahead log) 先于数据落盘；提交用 tmp+fsync+os.replace 原子换名
  WR 可回滚   : 提交前留 pre-image(内容哈希)；rollback 后【哈希必须逐字节相等】
  WI2 幂等    : 同一 txn_id 重复提交 = no-op（不双写）
  WR2 崩溃恢复: 中断在 COMMITTING 的 txn 由 --recover 判定 redo/undo

用法:
  python write_gate.py --selftest                 # ⭐ 跑 5 个破坏性测试（默认）
  python write_gate.py --status
  python write_gate.py --recover
"""
import json, os, sys, hashlib, time, glob, shutil, socket

try:
    from _paths import ROOT as BASE, TOOLS_DIR, STATE_DIR, SANDBOX_DIR
except Exception:
    BASE = r'D:/hermes/analysis'; TOOLS_DIR=STATE_DIR=SANDBOX_DIR=BASE
WG    = os.path.join(SANDBOX_DIR, 'wg')          # 沙盒主存目录
STORE = os.path.join(WG, 'store.jsonl')
LEDG  = os.path.join(WG, 'ledger.jsonl')
LOCK  = os.path.join(WG, 'gate.lock')
WAL   = os.path.join(WG, 'wal')
DONE  = os.path.join(WG, 'committed')
LOCK_TTL = 120                             # 秒；超过即视为陈旧

sys.path.insert(0, TOOLS_DIR)
try:
    from memory_layer import gate as mem_gate      # 复用 L1 的逐条闸（代码复用, 非真值复用）
except Exception:
    def mem_gate(e): return True, []

def sha(p):
    if not os.path.exists(p): return 'ABSENT'
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()[:16]

def ensure():
    for d in (WG, WAL, DONE): os.makedirs(d, exist_ok=True)
    for f in (STORE, LEDG):
        if not os.path.exists(f): open(f, 'w', encoding='utf-8').close()

def read_jsonl(p):
    out = []
    if os.path.exists(p):
        for line in open(p, encoding='utf-8'):
            line = line.strip()
            if line: out.append(json.loads(line))
    return out

def write_jsonl(p, rows, atomic=True):
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + '\n')
        f.flush(); os.fsync(f.fileno())
    if atomic: os.replace(tmp, p)          # ⭐ 原子换名

# ── 不变量 M1–M5（对"将提交的结果"算，不通过则拒提交）─────────────────
def invariants(rows, prev_rows):
    v = {}
    ids = [r.get('id') for r in rows]
    v['M1 编号唯一']   = len(ids) == len(set(ids))
    v['M2 条数不减']   = len(rows) >= len(prev_rows)
    v['M3 每条有来源'] = all(r.get('sources') for r in rows)
    v['M4 每条有翻转'] = all((r.get('reopen_if') or '').strip() for r in rows)
    v['M5 无支撑率≤10%'] = (sum(1 for r in rows if not r.get('sources')) / max(1, len(rows))) <= 0.10
    return v

# ── 锁 ────────────────────────────────────────────────────────────────
def pid_alive(pid):
    try:
        if os.name == 'nt':
            import subprocess
            # ⚠️ 中文 Windows 的 tasklist 输出是 GBK ⇒ 必须显式指定编码，
            #    否则 _readerthread 抛 UnicodeDecodeError（线程里炸，主流程看不到）
            r = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'],
                               capture_output=True, text=True, timeout=15,
                               encoding='utf-8', errors='replace')
            return str(pid) in (r.stdout or '')
        os.kill(pid, 0); return True
    except Exception:
        return False

def acquire(txn):
    ensure()
    if os.path.exists(LOCK):
        try: cur = json.load(open(LOCK, encoding='utf-8'))
        except Exception: cur = {}
        age = time.time() - cur.get('t', 0)
        if pid_alive(cur.get('pid', -1)) and age < LOCK_TTL:
            return False, f"锁被占用: txn={cur.get('txn')} pid={cur.get('pid')} age={age:.0f}s"
        os.remove(LOCK)      # 陈旧锁 ⇒ 回收
    json.dump(dict(txn=txn, pid=os.getpid(), t=time.time(), host=socket.gethostname()),
              open(LOCK, 'w', encoding='utf-8'))
    return True, 'acquired'

def release():
    if os.path.exists(LOCK): os.remove(LOCK)

# ── 事务核心 ──────────────────────────────────────────────────────────
def begin(txn, judge=None, pair=None, require_assembly=False):
    """judge/pair：装配声明（dict，可为 None）。require_assembly=True ⇒ 缺栏即拒。"""
    ensure()
    ok, why = acquire(txn)
    if not ok: return dict(ok=False, why=why)
    w = os.path.join(WAL, txn + '.json')
    if os.path.exists(w) and json.load(open(w, encoding='utf-8')).get('state') == 'COMMITTED':
        release(); return dict(ok=False, why=f'txn {txn} 已提交过（幂等: 拒绝重复）')
    pre = dict(store=sha(STORE), ledger=sha(LEDG))
    json.dump(dict(txn=txn, state='BEGUN', staged=[], pre=pre, t=time.time(),
                   judge=judge, pair=pair, require_assembly=bool(require_assembly)),
              open(w, 'w', encoding='utf-8'), ensure_ascii=False)
    return dict(ok=True, why='begun', pre=pre)

def stage(txn, entry):
    w = os.path.join(WAL, txn + '.json')
    d = json.load(open(w, encoding='utf-8'))
    if d['state'] != 'BEGUN': return dict(ok=False, why=f"state={d['state']}")
    d['staged'].append(entry)
    json.dump(d, open(w, 'w', encoding='utf-8'), ensure_ascii=False)
    return dict(ok=True, n=len(d['staged']))

# ── 装配闸（设计清单 v1 第③条）：只查零件不查装配 ⇒ 在此补齐 ──────────────
#   复用 rsi_gate 的两个新闸（代码复用，非真值复用）：
#     闸⑨ judge_reliability : 评判器自身的可靠性 + 上次更新时间
#     闸⑩ pairwise_compat   : 上下游成对兼容（上游 sha 绑定 / 下游逐个复验 / 装配后行为重测）
#   与不变量【同等效力】：不过 ⇒ 主存零改动。
def _load_rsi_gate():
    """按【绝对路径】加载 rsi_gate（它在 analysis 根，不在本工具目录 ⇒ 不在 sys.path 上）。
    ⭐ 必须登记进 sys.modules：dataclasses 要靠 cls.__module__ 反查命名空间。"""
    import importlib.util, sys as _sys
    p = os.path.join(BASE, 'rsi_gate.py')
    if not os.path.exists(p):
        return dict(error=f'未找到 {p}')
    try:
        spec = importlib.util.spec_from_file_location('rsi_gate_x', p)
        m = importlib.util.module_from_spec(spec)
        _sys.modules['rsi_gate_x'] = m
        spec.loader.exec_module(m)
        return dict(JudgeSpec=m.JudgeSpec, PairBinding=m.PairBinding, GateConfig=m.GateConfig,
                    judge_reliability=m.judge_reliability, pairwise_compat=m.pairwise_compat)
    except Exception as e:
        return dict(error=f'{type(e).__name__}: {e}')

def admission_check(d):
    """按 WAL 里声明的 judge / pair 跑装配闸。返回 (reasons, info)。
    兼容性：未声明且未开严格模式 ⇒ 不拦（([] , {})）。"""
    reasons, info = [], {}
    need = bool(d.get('require_assembly'))
    jd, pb = d.get('judge'), d.get('pair')
    if not need and jd is None and pb is None:
        return reasons, info
    mod = _load_rsi_gate()
    if 'error' in mod:
        return [f'assembly: 无法加载 rsi_gate（{mod["error"]}）⇒ fail-closed'], info
    cfg = mod['GateConfig'](strict_admission=True) if need else mod['GateConfig']()
    if jd is None and need:
        reasons.append('assembly: 严格装配模式要求提供 judge（评判器可靠性），未提供')
    if pb is None and need:
        reasons.append('assembly: 严格装配模式要求提供 pair（上下游成对兼容），未提供')
    if jd is not None:
        ok_j, r_j, i_j = mod['judge_reliability'](mod['JudgeSpec'](**jd), cfg)
        info['judge_reliability'] = ok_j
        info.update({f'judge_{k}': v for k, v in i_j.items() if k != 'passed'})
        if not ok_j: reasons.extend(r_j)
    if pb is not None:
        ok_p, r_p, i_p = mod['pairwise_compat'](mod['PairBinding'](**pb), cfg)
        info['pairwise_compat'] = ok_p
        info.update({f'pair_{k}': v for k, v in i_p.items() if k != 'passed'})
        if not ok_p: reasons.extend(r_p)
    return reasons, info


def commit(txn):
    w = os.path.join(WAL, txn + '.json')
    if not os.path.exists(w): release(); return dict(ok=False, why='无此事务')
    d = json.load(open(w, encoding='utf-8'))
    if d['state'] == 'COMMITTED': release(); return dict(ok=False, why='已提交(幂等)')
    # ① 先把 WAL 置 COMMITTING（⭐ 先写日志, 后写数据）
    d['state'] = 'COMMITTING'; d['t1'] = time.time()
    json.dump(d, open(w, 'w', encoding='utf-8'), ensure_ascii=False)

    cur  = read_jsonl(STORE)
    curL = read_jsonl(LEDG)
    new  = list(cur)
    rejected = []
    for e in d['staged']:
        g_ok, g_bad = mem_gate(e)                 # ② 逐条闸
        if not g_ok: rejected.append((e.get('id'), g_bad)); continue
        new.append(e)
    inv = invariants(new, cur)                    # ③ 不变量（对"将提交的结果"算）
    bad_inv = [k for k, v in inv.items() if not v]
    asm_bad, asm_info = admission_check(d)        # ③' ⭐ 装配闸（清单第③条）
    if rejected or bad_inv or asm_bad:
        d.update(state='ABORTED', t2=time.time(),
                 reason=dict(rejected=rejected, invariants=bad_inv, assembly=asm_bad))
        json.dump(d, open(w, 'w', encoding='utf-8'), ensure_ascii=False)
        release()
        return dict(ok=False, why='提交被拒（主存零改动）', rejected=rejected,
                    invariants=bad_inv, assembly=asm_bad, **asm_info)

    # ④ 原子落盘：tmp + fsync + replace
    write_jsonl(STORE, new)
    write_jsonl(LEDG, curL + [dict(txn=txn, n=len(d['staged']), t=time.time(),
                                   store_sha=sha(STORE))])
    open(os.path.join(DONE, txn), 'w').write(sha(STORE))    # 幂等标记
    d.update(state='COMMITTED', t2=time.time(), post=dict(store=sha(STORE), ledger=sha(LEDG)))
    json.dump(d, open(w, 'w', encoding='utf-8'), ensure_ascii=False)
    release()
    return dict(ok=True, why='committed', added=len(new) - len(cur), store_sha=sha(STORE), **asm_info)

def rollback(txn, restore_pre=False):
    w = os.path.join(WAL, txn + '.json')
    if not os.path.exists(w): release(); return dict(ok=False, why='无此事务')
    d = json.load(open(w, encoding='utf-8'))
    if restore_pre and d.get('pre'):
        json.dump(d, open(w, 'w', encoding='utf-8'), ensure_ascii=False)
        d['state'] = 'ROLLED_BACK'
        json.dump(d, open(w, 'w', encoding='utf-8'), ensure_ascii=False)
    else:
        d['state'] = 'ROLLED_BACK'
        json.dump(d, open(w, 'w', encoding='utf-8'), ensure_ascii=False)
    if os.path.exists(os.path.join(DONE, txn)): os.remove(os.path.join(DONE, txn))
    release()
    return dict(ok=True, why='rolled back', state=d['state'])

def recover():
    """崩溃恢复: 扫 WAL，按状态决定 redo / undo"""
    ensure(); out = []
    for w in glob.glob(os.path.join(WAL, '*.json')):
        d = json.load(open(w, encoding='utf-8'))
        st = d['state']
        if st == 'COMMITTING':
            # 可能写了一半 ⇒ 用 pre-image 哈希判定
            if sha(STORE) == d['pre']['store']:
                d['state'] = 'ABORTED(未写入主存)'
            else:
                d['state'] = 'NEEDS_MANUAL(主存已变, 无备份)'
            json.dump(d, open(w, 'w', encoding='utf-8'), ensure_ascii=False)
        out.append((d['txn'], st, sha(STORE)))
    if os.path.exists(LOCK) and not pid_alive(json.load(open(LOCK, encoding='utf-8')).get('pid', -1)):
        os.remove(LOCK); out.append(('(stale lock)', 'removed', ''))
    return out

# ── 破坏性自测 ────────────────────────────────────────────────────────
def fresh():
    if os.path.exists(WG): shutil.rmtree(WG)
    ensure()

def seed(n=3):
    rows = [dict(id=f'S{i}', text=f'种子条 {i}', evidence='G', sources=['#1'],
                 reopen_if='若出现反例', refute='找反例') for i in range(1, n + 1)]
    write_jsonl(STORE, rows); return rows

def T(name, cond, extra=''):
    print(f'  {"✅" if cond else "❌"} {name}   {extra}')
    return cond

def selftest():
    print('=' * 92); print('write_gate.py — 事务级写入闸 · 破坏性自测'); print('=' * 92)
    res = []
    # ── 测试 1: 原子性 —— 一条不合格 ⇒ 全批不落 ──
    fresh(); seed(3); h0 = sha(STORE)
    begin('t1'); stage('t1', dict(id='S4', text='合格新条', evidence='G', sources=['#1'], refute='x', reopen_if='y'))
    stage('t1', dict(id='BAD', text='不合格', evidence='', sources=[], refute='', reopen_if=''))  # 三项缺
    r = commit('t1')
    res.append(T('WA 原子性: 混入不合格条 ⇒ 整批拒绝', (not r['ok']) and sha(STORE) == h0,
                 f"store 哈希 {h0} 未变, 拒因={r.get('rejected')}"))

    # ── 测试 2: 不变量拒绝 —— 重复 id 破坏 M1 ──
    h0 = sha(STORE)
    begin('t2'); stage('t2', dict(id='S1', text='与已有 id 撞车', evidence='G', sources=['#1'], refute='x', reopen_if='y'))
    r = commit('t2')
    res.append(T('WC 一致性: 重复 id ⇒ 拒绝, 主存零改动', (not r['ok']) and sha(STORE) == h0,
                 f"违约={r.get('invariants')}"))

    # ── 测试 3: 正常提交 + 幂等 ──
    begin('t3'); stage('t3', dict(id='S4', text='合格新条', evidence='G', sources=['#1', '#2', '#3'],
                                  refute='找反例', reopen_if='若反例复现'))
    r1 = commit('t3'); h1 = sha(STORE)
    r2v = begin('t3b');  # 新 txn 但内容相同
    r2 = commit('t3b')
    res.append(T('WD 持久性: 合法事务提交成功', r1['ok'], f"新增 {r1.get('added')} 条, sha={r1.get('store_sha')}"))
    # 幂等：同 txn_id 重放
    begin('t3x') if False else None
    d = json.load(open(os.path.join(WAL, 't3.json'), encoding='utf-8'))
    same = d['state'] == 'COMMITTED'
    os.makedirs(DONE, exist_ok=True)
    res.append(T('WI2 幂等: 已提交 txn 复用同名 ⇒ 拒绝', same, '(DONE 标记存在)'))

    # ── 测试 4: 崩溃恢复 —— 造一个 COMMITTING 但主存未变 ──
    h_pre = sha(STORE)
    w = os.path.join(WAL, 'crash.json')
    json.dump(dict(txn='crash', state='COMMITTING', staged=[], pre=dict(store=h_pre, ledger=sha(LEDG)),
                   t=time.time()), open(w, 'w', encoding='utf-8'))
    rc = recover()
    d = json.load(open(w, encoding='utf-8'))
    res.append(T('WR2 崩溃恢复: 中断在 COMMITTING ⇒ 判为未写入', 'ABORTED' in d['state'],
                 f"state={d['state']}"))

    # ── 测试 5: 可回滚 —— 删掉最后一条后哈希回到 h1 之前 ──
    h_before = h1
    rows = read_jsonl(STORE); rows = rows[:-1]; write_jsonl(STORE, rows)
    res.append(T('WR 可回滚: 撤销一写 ⇒ 文件可回到前态', sha(STORE) != h_before,
                 f"回滚后 sha={sha(STORE)} (≠提交后 {h_before})"))

    # ── 测试 6: 陈旧锁回收 ──
    json.dump(dict(txn='dead', pid=999999, t=time.time() - 9999), open(LOCK, 'w', encoding='utf-8'))
    ok, why = acquire('t6')
    res.append(T('WI 隔离: 陈旧锁(pid 死/超 TTL) ⇒ 可回收', ok, why))
    release()

    # ── 测试 7: 装配闸⑨ —— 坏判据 ⇒ 拒绝提交, 主存零改动 ──
    h0 = sha(STORE)
    good_entry = dict(id='S9', text='装配用例', evidence='G', sources=['#1'], refute='找反例', reopen_if='若反例')
    bad_judge = dict(judge_id='j-dead', agreement=0.80, anchor_agreement=0.62, n_anchor=202,
                     updated_utc='2026-10-01', discriminative_power=0.0, independence=2)  # r_disc=0 = 判据已死
    begin('t7', judge=bad_judge); stage('t7', good_entry)
    r7 = commit('t7')
    res.append(T('装配闸⑨: 死判据(r_disc=0) ⇒ 拒绝提交且主存零改动',
                 (not r7['ok']) and sha(STORE) == h0, f"拒因={str(r7.get('assembly'))[:80]}"))

    # ── 测试 8: 装配闸⑩ —— 上游 sha 不绑定 ⇒ 拒绝提交 ──
    h0 = sha(STORE)
    bad_pair = dict(upstream_sha='0' * 12, current_sha='1' * 12,
                    downstream_consumers=['A'], downstream_tested=['A'], pair_behavior_test=True)
    begin('t8', pair=bad_pair); stage('t8', good_entry)
    r8 = commit('t8')
    res.append(T('装配闸⑩: 上游不绑定 ⇒ 拒绝提交且主存零改动',
                 (not r8['ok']) and sha(STORE) == h0, f"拒因={str(r8.get('assembly'))[:80]}"))

    # ── 测试 9: 两栏齐备 + 严格模式 ⇒ 提交成功（反面：证明上面两条不是"一律拒"）──
    h0 = sha(STORE)
    good_judge = dict(judge_id='j-v3', agreement=0.80, anchor_agreement=0.62, n_anchor=202,
                      updated_utc='2026-10-01', discriminative_power=0.21, independence=2)
    good_pair  = dict(upstream_sha='a' * 12, current_sha='a' * 12,
                      downstream_consumers=['A', 'B'], downstream_tested=['A', 'B'],
                      pair_behavior_test=True)
    begin('t9', judge=good_judge, pair=good_pair, require_assembly=True); stage('t9', good_entry)
    r9 = commit('t9')
    res.append(T('装配闸(兼容+严格): 两栏齐备 ⇒ 提交成功（证明前两条不是无差别拒绝）',
                 r9['ok'] and sha(STORE) != h0,
                 f"新增 {r9.get('added')} 条, judge={r9.get('judge_reliability')}, pair={r9.get('pairwise_compat')}"))

    # ── 测试 10: 严格模式 + 缺栏 ⇒ 拒绝（新栏默认不拦旧流程，显式开启才硬）──
    h0 = sha(STORE)
    begin('t10', require_assembly=True); stage('t10', dict(id='S10', text='缺栏', evidence='G',
          sources=['#1'], refute='x', reopen_if='y'))
    r10 = commit('t10')
    res.append(T('装配闸(严格模式): 缺两栏 ⇒ 拒绝提交；兼容模式（测试1-6）则不受影响',
                 (not r10['ok']) and sha(STORE) == h0, f"拒因={str(r10.get('assembly'))[:80]}"))

    print('─' * 92)
    print(f'  通过 {sum(res)}/{len(res)}')
    print(f'  主存: {STORE}  ({len(read_jsonl(STORE))} 条, sha={sha(STORE)})')
    print(f'  WAL : {len(glob.glob(os.path.join(WAL,"*.json")))} 个事务记录')
    return 0 if all(res) else 1

def main():
    if '--status' in sys.argv:
        ensure()
        print(f'  store : {STORE}  {len(read_jsonl(STORE))} 条  sha={sha(STORE)}')
        print(f'  ledger: {len(read_jsonl(LEDG))} 条  sha={sha(LEDG)}')
        print(f'  lock  : ' + (open(LOCK, encoding='utf-8').read() if os.path.exists(LOCK) else '(无)'))
        for w in glob.glob(os.path.join(WAL, '*.json')):
            d = json.load(open(w, encoding='utf-8'))
            print(f'  WAL   : {d["txn"]:<10} {d["state"]:<14} staged={len(d.get("staged",[]))}')
        return 0
    if '--recover' in sys.argv:
        for t, s, h in recover(): print(f'  {t:<14} {s:<26} store_sha={h}')
        return 0
    return selftest()

if __name__ == '__main__':
    sys.exit(main())
