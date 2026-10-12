#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
baseline.py — 基线脚本（全栈收口）

一个命令回答: 系统现在健康吗? 和基线比, 是【增长】还是【退化】?

三层职责:
  ① 采集(collect) : 现算所有可复核的量 —— 【不读记忆里的数】, 一律回实际源
  ② 冻结(freeze)  : 写 baseline.json（含每项的定义 + 阈值 + 时间戳）
  ③ 比对(compare) : 与基线逐项比, 判决四类 —— 增长✅ / 保持✅ / 漂移⚠️ / 退化❌

判决规则（⭐ 关键是区分"增长"与"退化"）:
  单调不减类 (条目数/铁律数/审计行/器 exit=0): 减 = 退化
  布尔类     (编号连续/不变量/无自确认闭环): False = 退化
  体量类     (KB/行数): 增=合法(追加式归档); 骤降>5% = 退化
  hash 类    (冻结/凭据): 变 = 漂移(需人工确认是有意变更)

强制件:
  · --selftest: 注入 3 种【假退化】, 必须全被抓到 —— 否则判据是恒真的(9999× 的教训)
  · 每项都写清【观测量/阈值/阈值附近怎么办】(#175)

用法: python baseline.py --freeze | --check | --selftest
"""
import os, sys, json, hashlib, subprocess, time, re

try:
    from _paths import ROOT as BASE, TOOLS_DIR, STATE_DIR, SANDBOX_DIR
except Exception:
    BASE = r'D:/hermes/analysis'; TOOLS_DIR=STATE_DIR=SANDBOX_DIR=BASE
ARCH = os.path.join(BASE, 'PAPER_ARCHIVE_agent_memory_swarm_2026-10.md')
CHECK= os.path.join(BASE, 'AGENT_MEMORY_COORD_DESIGN_CHECKLIST_v1.md')
BASE_JSON = os.path.join(STATE_DIR, 'baseline.json')
TOOLS = ['rsi_gate.py', 'cluster_audit.py', 'persist_audit.py', 'memory_layer.py',
         'meta_recursion.py', 'write_gate.py', 'repro_audit.py', 'verify_layer_v2.py']

# ── 判据登记: 每项带 观测量 / 阈值 / 阈值附近怎么办 (#175) ──────────
RULES = {
 'arch_entries':   dict(kind='monotone', label='归档条目数',   thr='只增不减',      edge='减 1 也判退化(内容不会自己消失)'),
 'arch_iron':      dict(kind='monotone', label='跨篇铁律条数', thr='只增不减',      edge='同上'),
 'arch_kb':        dict(kind='size',     label='归档体积 KB',  thr='增≤+20%/次',   edge='降幅>5% 判退化; 单次增>20% 需人工确认'),
 'arch_lines':     dict(kind='size',     label='归档行数',     thr='增≤+20%/次',   edge='降幅>5% 判退化'),
 'arch_numbering': dict(kind='bool',     label='编号连续1..N', thr='必须 True',    edge='False 即退化'),
 'checklist_kb':   dict(kind='size',     label='清单体积 KB',  thr='增≤+20%/次',   edge='降幅>5% 判退化'),
 'tools_exit0':    dict(kind='monotone', label='八器退出码全 0', thr='必须全 0',   edge='任一非 0 即退化'),
 'wg_store_sha':   dict(kind='hash',     label='事务闸主存 sha', thr='变化需人工确认', edge='变=漂移'),
 'anchor_sha':     dict(kind='hash',     label='锚点冻结 sha',  thr='变化需人工确认', edge='变=漂移(或有意重定锚点)'),
 'arch_sha':       dict(kind='hash',     label='归档文件 sha',  thr='变化=有写入',  edge='任意变化都需在台账留痕'),
}

def sha(p, n=16):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()[:n] if os.path.exists(p) else 'ABSENT'

def count_iron(t):
    m = re.search(r'^(#{1,4})\s*跨论文铁律.*$', t, re.M)
    if not m: return None
    lvl = len(m.group(1))
    nxt = re.search(r'^#{1,%d}\s' % lvl, t[m.end():], re.M)
    seg = t[m.start(): m.end() + nxt.start()] if nxt else t[m.start():]
    return len(re.findall(r'^\s*(\d{1,3})[\.\)、]\s', seg, re.M))

def collect_tools():
    codes = {}
    for f in TOOLS:
        p = os.path.join(BASE, f) if os.path.exists(os.path.join(BASE, f)) else os.path.join(TOOLS_DIR, f)
        codes[f] = 2 if not os.path.exists(p) else \
            subprocess.run(['python', f], cwd=BASE if os.path.exists(os.path.join(BASE, f)) else TOOLS_DIR, capture_output=True, timeout=900).returncode
    return codes

def collect_files():
    """⭐ 快路径: 只读文件, 不跑器（供 selftest 的注入测试用）"""
    out = {}
    if not os.path.exists(ARCH): return out
    t = open(ARCH, encoding='utf-8', errors='replace').read()
    heads = sorted(set(int(x) for x in re.findall(r'^###\s*#?(\d{1,3})[\.\s:：]', t, re.M)))
    out['arch_entries']   = len(heads)
    out['arch_iron']      = count_iron(t)
    out['arch_kb']        = os.path.getsize(ARCH) // 1024
    out['arch_lines']     = t.count('\n') + 1
    out['arch_numbering'] = bool(heads) and heads == list(range(1, heads[-1] + 1))
    out['arch_sha']       = sha(ARCH)
    out['checklist_kb']   = (os.path.getsize(CHECK) // 1024) if os.path.exists(CHECK) else None
    out['wg_store_sha'] = sha(os.path.join(SANDBOX_DIR, 'wg', 'store.jsonl'))
    out['anchor_sha']   = (json.load(open(os.path.join(STATE_DIR, 'anchor_lock.json'), encoding='utf-8'))['sha']
                           if os.path.exists(os.path.join(STATE_DIR, 'anchor_lock.json')) else 'ABSENT')
    return out

def collect():
    """⭐ 一律现算, 不读任何记忆里的数"""
    out = collect_files()
    out['tools_exit0'] = all(v == 0 for v in collect_tools().values())
    return out

def freeze():
    cur = collect()
    snap = dict(t=time.strftime('%Y-%m-%d %H:%M:%S'), metrics=cur, rules=RULES)
    json.dump(snap, open(BASE_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'已冻结基线 → {BASE_JSON}')
    for k, v in cur.items():
        if k.startswith('_'): continue
        print(f'  {k:<16}{str(v):>10}   {RULES.get(k,{}).get("label","")}')
    return 0

def compare(cur, base):
    """返回 [(项, 前, 后, 判决, 说明)]；判决 ∈ {增长✅, 保持✅, 漂移⚠️, 退化❌}"""
    rows = []
    for k, rule in RULES.items():
        if k not in cur or k not in base: continue
        a, b = base[k], cur[k]
        kind = rule['kind']
        if kind == 'monotone':
            if isinstance(a, bool) or isinstance(b, bool):
                v = '保持✅' if b else '退化❌'
            else:
                v = '增长✅' if b > a else ('保持✅' if b == a else '退化❌')
        elif kind == 'bool':
            v = '保持✅' if b else '退化❌'
        elif kind == 'size':
            if b < a * 0.95: v = '退化❌'
            elif b > a * 1.20: v = '漂移⚠️'
            else: v = '增长✅'
        elif kind == 'hash':
            v = '保持✅' if b == a else '漂移⚠️'
        else:
            v = '⚠️'
        rows.append((rule['label'], a, b, v, rule['edge']))
    return rows

def check():
    if not os.path.exists(BASE_JSON):
        print('无基线 ⇒ 先跑 python baseline.py --freeze'); return 0
    snap = json.load(open(BASE_JSON, encoding='utf-8'))
    print('=' * 100)
    print(f'基线比对  (冻结于 {snap["t"]})')
    print('=' * 100)
    cur = collect()
    rows = compare(cur, snap['metrics'])
    bad = 0
    for label, a, b, v, edge in rows:
        if v.startswith('退化'): bad += 1
        print(f'  {label:<16}{str(a):>10} → {str(b):>10}   {v:<8}{("" if v.endswith("✅") else "  "+edge)}')
    print('─' * 100)
    n_bad = sum(1 for r in rows if r[3].startswith('退化'))
    n_drift = sum(1 for r in rows if r[3].startswith('漂移'))
    print(f'  退化 {n_bad} · 漂移 {n_drift} · 共 {len(rows)} 项')
    print('  ⭐ 判决: ' + ('✅ 无退化' if n_bad == 0 else f'❌ 检出 {n_bad} 项退化'))
    return 1 if n_bad else 0

def selftest():
    """⭐⭐ 注入【假退化】必须被抓住 —— 否则判据是恒真的（9999× 的教训）"""
    print('=' * 100)
    print('基线脚本自检: 注入假退化, 必须全被抓到')
    print('=' * 100)
    if not os.path.exists(BASE_JSON):
        print('  无基线 ⇒ 先跑 --freeze'); return 1
    snap = json.load(open(BASE_JSON, encoding='utf-8'))
    base = snap['metrics']
    cur = dict(base)
    cases = []
    # ① 条目数 −1（内容凭空消失 ⇒ 必须判退化）
    c1 = dict(cur); c1['arch_entries'] = base['arch_entries'] - 1
    cases.append(('条目数 -1', c1, 'arch_entries'))
    # ② 铁律 −1
    c2 = dict(cur); c2['arch_iron'] = (base['arch_iron'] or 1) - 1
    cases.append(('铁律 -1', c2, 'arch_iron'))
    # ③ 体积骤降 10%
    c3 = dict(cur); c3['arch_kb'] = int(base['arch_kb'] * 0.90)
    cases.append(('体积 -10%', c3, 'arch_kb'))
    # ④ 编号断裂
    c4 = dict(cur); c4['arch_numbering'] = False
    cases.append(('编号断裂', c4, 'arch_numbering'))
    # ⑤ 一器非 0
    c5 = dict(cur); c5['tools_exit0'] = False
    cases.append(('某器 exit≠0', c5, 'tools_exit0'))
    ok = 0
    for name, cc, key in cases:
        rows = {r[0]: r[3] for r in compare(cc, base)}
        hit = any(v.startswith('退化') for v in rows.values())
        print(f'  {"✅" if hit else "❌ 漏检!"} 注入「{name}」 ⇒ {rows.get(RULES[key]["label"],"?")}')
        ok += hit
    # ⑥ 反面对照: 什么都不动 ⇒ 必须【不】报退化（防止"逢动必报"）
    rows = {r[0]: r[3] for r in compare(base, base)}
    quiet = not any(v.startswith('退化') for v in rows.values())
    print(f'  {"✅" if quiet else "❌ 误报!"} 不注入任何变化 ⇒ 应无退化')
    print('─' * 100)
    print(f'  假退化抓取 {ok}/{len(cases)} · 反面对照 {"通过" if quiet else "失败"}')

    # ⑦ ⭐⭐ 采集器非恒真校准（防"compare 能抓但 collect 是死的"）
    #    上一次我写了个【恒真】的判据(9999×), 所以这里必须真改文件再还原
    print('\n  ⑦ 采集器端到端校准: 真改文件 ⇒ collect_files() 必须看得见 ⇒ 再还原')
    orig = open(ARCH, 'rb').read()
    probe = b'\n<!-- baseline selftest probe -->\n'
    try:
        c_before = collect_files()
        with open(ARCH, 'ab') as f:
            f.write(probe); f.flush(); os.fsync(f.fileno())
        c_after = collect_files()
        moved = (c_after['arch_lines'] != c_before['arch_lines']) and \
                (c_after['arch_kb'] >= c_before['arch_kb']) and \
                (c_after['arch_sha'] != c_before['arch_sha'])
        print(f'    {"✅" if moved else "❌ collect() 看不见文件变化!"} '
              f'行数 {c_before["arch_lines"]}→{c_after["arch_lines"]} · sha {c_before["arch_sha"]}→{c_after["arch_sha"]}')
    finally:
        open(ARCH, 'wb').write(orig)                    # 逐字节还原
    c_restored = collect_files()
    same = (c_restored['arch_sha'] == c_before['arch_sha'] and
            c_restored['arch_lines'] == c_before['arch_lines'] and
            open(ARCH, 'rb').read() == orig)
    print(f'    {"✅" if same else "❌ 还原不干净!"} 逐字节还原  sha={c_restored["arch_sha"]} '
          f'(原 {c_before["arch_sha"]})')
    print('─' * 100)
    allok = (ok == len(cases)) and quiet and moved and same
    print('  ⇒ ' + ('✅ 判据非恒真、不误报、采集器活的、且可无损还原' if allok else '❌ 判据不可信'))
    return 0 if allok else 1

if __name__ == '__main__':
    if '--freeze' in sys.argv: sys.exit(freeze())
    if '--selftest' in sys.argv: sys.exit(selftest())
    sys.exit(check())
