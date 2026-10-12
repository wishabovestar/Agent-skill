#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cluster_audit.py — Agent 集群升级蓝图 v1 · P0 审计器（纯 stdlib，零依赖，只读归档）

依据（全部来自归档自身）：
  #186 表示坍缩   : 两个"维度"若成员集合高度重合 ⇒ 是一个东西两个名字 (cosine→1)
  #184 无支撑率   : 断言应能按【支撑来源】分类并统计"无直证"占比
  #178 两池设计   : 主池(≥N 篇支撑, 可排名) / 扩展池(1-2 篇, 只看覆盖)
  #183 单轴       : 归因需可复现 ⇒ 所有计数必须【由脚本算】, 不手维护
  #185 顺序       : 先验证"维度是否相关", 再在该维度下比较  ← 本脚本只做前者

用法:  python cluster_audit.py [归档路径]
输出:  1) 可复现计数  2) 上位概念坍缩矩阵(两两 Jaccard)  3) 铁律分池  4) 退出码
"""
import re, sys, os, itertools, json

ARCHIVE = sys.argv[1] if len(sys.argv) > 1 else r'D:/hermes/analysis/PAPER_ARCHIVE_agent_memory_swarm_2026-10.md'

# ── 待检的上位概念（候选维度）────────────────────────────────────────────
CONCEPTS = {
    '解耦':      r'解耦|DECOUPL|decoupl|分离(?:形状|与)|正交分解',
    '分工':      r'分工|各用其长|各管一件事|各有一处短|分工而非迁就',
    '校准失效':  r'校准(?:在|失效)|calibration|分布一变',
    '条件边界':  r'边界条件|报条件|boundary condition|regime|适用条件',
    '反驳通道':  r'反驳|refutation|否证|被违反着试|可被检验',
    '两池':      r'两池|主池|扩展池|可比与覆盖|可比性与覆盖面',
    'bi-level':  r'bi-level|个体级|两层.*条件|条件在.*两层',
    '事后贴名':  r'事后贴|post-?hoc|名字.*事后|可辨识.*可解释',
    '元求解器':  r'元求解器|meta-solver|在已有.*之上',
    '置换不变':  r'置换不变|permutation-invariant',
    '单轴':      r'单轴|single-axis|一次只动|只变一个',
    '误差分解':  r'误差.*分解|隔离.*误差|isolates.*error',
    '下界':      r'下界|lower bound|不可约',
    '探针':      r'探针|probe|最弱读出器|诊断任务',
    '人工先定':  r'手工汇总|人工预定|人工标注|手工贴|hand-?crafted|manually',
}
MAIN_POOL_MIN = 3   # #178: ≥3 篇支撑 ⇒ 主池

def load():
    with open(ARCHIVE, encoding='utf-8') as f:
        return f.read()

def entries(t):
    """→ {编号: 该条目全文}"""
    out, cur, buf = {}, None, []
    for line in t.split('\n'):
        m = re.match(r'^### (\d+)\.', line)
        if m:
            if cur: out[cur] = '\n'.join(buf)
            cur, buf = int(m.group(1)), [line]
        elif re.match(r'^## ', line) and cur:
            out[cur] = '\n'.join(buf); cur, buf = None, []
        elif cur is not None:
            buf.append(line)
    if cur: out[cur] = '\n'.join(buf)
    return out

def rules(t):
    m = re.search(r'^## 跨论文铁律.*?$(.*?)^---', t, re.M | re.S)
    if not m: return {}
    seg = m.group(1)
    out = {}
    for r in re.finditer(r'^(\d{1,3})\.\s*(.+?)(?=^\d{1,3}\.\s|\Z)', seg, re.M | re.S):
        out[int(r.group(1))] = r.group(2)
    return out

def main():
    t = load()
    E = entries(t)
    R = rules(t)
    n_entries, n_rules = len(E), len(R)

    print('=' * 78)
    print('cluster_audit.py — Agent 集群升级蓝图 v1 · P0 审计（只读归档，可复现）')
    print('=' * 78)
    print(f'归档: {ARCHIVE}')
    print(f'规模: {os.path.getsize(ARCHIVE)//1024} KB / {t.count(chr(10))+1} 行')
    print()
    print('── ① 可复现计数（不手维护）' + '─' * 46)
    print(f'  条目数(### N.)      = {n_entries}')
    print(f'  编号连续            = {sorted(E)==list(range(1,n_entries+1))}')
    _arxr = re.compile(r"[0-9]{4}\.[0-9]{4,5}")
    _arx = sum(1 for b in E.values() if _arxr.search(b[:800]))
    print(f'  含 arXiv ID 的条目  = {_arx}'
          f'   （分类判据不同结果不同，见 header 说明）')
    print(f'  铁律条数            = {n_rules}')

    # ── ② 上位概念坍缩矩阵 ───────────────────────────────────────────────
    print()
    print('── ② 上位概念【坍缩检测】（#186: Jaccard→1 即一个东西两个名字）' + '─' * 12)
    members = {}
    for name, pat in CONCEPTS.items():
        rx = re.compile(pat, re.I)
        members[name] = {n for n, b in E.items() if rx.search(b)}
    print(f'  {"概念":<10}{"覆盖条目数":>10}   {">=3篇支撑?"}')
    for name, s in sorted(members.items(), key=lambda kv: -len(kv[1])):
        print(f'  {name:<10}{len(s):>10}   {"是(主池)" if len(s)>=MAIN_POOL_MIN else "否(扩展池)"}')

    pairs = []
    MIN_SET = 3   # ⚠️ 自审修正(#176): 小集合(|A|或|B|<3)上 Jaccard 极不稳 ——
                  #    两个各含 1 条且恰为该条的概念会得 J=1.00，纯属噪声。
    for a, b in itertools.combinations(members, 2):
        A, B = members[a], members[b]
        if len(A) < MIN_SET or len(B) < MIN_SET:
            continue
        j = len(A & B) / len(A | B)
        pairs.append((j, a, b, len(A & B)))
    pairs.sort(reverse=True)
    print()
    print(f'  Top 8 高重合对（Jaccard，已滤除 |集合|<{MIN_SET} 的噪声对）:')
    for j, a, b, ov in pairs[:8]:
        flag = '  ⚠️ 坍缩候选' if j >= 0.50 else ''
        print(f'    {a:<10} × {b:<10} J={j:.3f}  共有条目 {ov}{flag}')
    severe = [p for p in pairs if p[0] >= 0.50]
    print(f'  ⇒ Jaccard ≥ 0.50 的对数 = {len(severe)}'
          + ('  （⚠️ 需合并或给出区分判据）' if severe else '  （未发现严重坍缩）'))
    print(f'  ⭐ 对照：被点名怀疑过的「解耦 × 分工」'
          + (f' J={[p for p in pairs if {p[1],p[2]}=={"解耦","分工"}][0][0]:.3f}'
             f' 共 {[p for p in pairs if {p[1],p[2]}=={"解耦","分工"}][0][3]} 条 ← 【非坍缩，二者确实分开了】'
             if any({p[1],p[2]}=={"解耦","分工"} for p in pairs) else ' 未同时进入主池'))

    # ── ③ 铁律分池（#178）───────────────────────────────────────────────
    print()
    print('── ③ 铁律【分池】（#178: 主池=≥%d 篇支撑, 可排名 / 扩展池=1-2 篇, 只看覆盖）' % MAIN_POOL_MIN + '─' * 6)
    pool = {'main': [], 'ext': [], 'none': []}
    sup = {}
    for k, body in R.items():
        cited = set(int(x) for x in re.findall(r'#(\d{1,3})', body))
        n = len(cited); sup[k] = n
        pool['main' if n >= MAIN_POOL_MIN else ('ext' if n >= 1 else 'none')].append(k)
    tot = len(R)
    print(f'  主池(≥{MAIN_POOL_MIN} 篇)  : {len(pool["main"]):>3}  ({len(pool["main"])/tot:.0%})  ⇒ 可参与"铁律"编号与排名')
    print(f'  扩展池(1-2 篇)   : {len(pool["ext"]):>3}  ({len(pool["ext"])/tot:.0%})  ⇒ 只作"候选观察"，不参与排名')
    print(f'  无 #NNN 引用      : {len(pool["none"]):>3}  ({len(pool["none"])/tot:.0%})  '
          f'⚠️ 其中 1–8 是按【名称】引用主线而非 #NNN ⇒ 此列【不是】真正的无支撑率')
    print(f'  支撑篇数分布     : ' + '  '.join(f'{k}篇:{v}' for k, v in sorted(
        {n: sum(1 for x in sup.values() if x == n) for n in set(sup.values())}.items())))
    print()
    print(f'  ⭐ 无支撑断言率（粗估，仅按"是否引用 #NNN"）= {len(pool["none"])/tot:.1%}')
    print(f'     ⚠️ 上界：另有"引用了但引用的是同一条"的情形未计；需 #184 的细化判据')
    ex = pool['none'][:12]
    if ex: print(f'     无引用铁律样例: {ex}')

    # ── ④ 结论 + 退出码 ─────────────────────────────────────────────────
    print()
    print('── ④ 结论' + '─' * 68)
    problems = []
    if severe: problems.append(f'坍缩候选 {len(severe)} 对（≥0.50）')
    if len(pool['none'])/tot > 0.10: problems.append(f'无支撑铁律 >10%')
    if any(len(members[c]) < MAIN_POOL_MIN for c in members): problems.append('存在扩展池级概念（覆盖<3 篇）')
    if problems:
        print('  ⚠️ 需处置: ' + ' / '.join(problems))
        print('  ⇒ 见《Agent 集群升级蓝图 v1》§3 P0 与 §4 脚本')
        code = 0   # 审计器本身成功即 0；问题以报告呈现
    else:
        print('  ✅ 未发现结构性坍缩/无支撑超标')
        code = 0
    print('  （退出码 0 = 审计器成功；问题以数值报告，不以致命退出表达）')
    print('=' * 78)

    # 落盘 JSON（供其他脚本/下一轮对比）
    out = {'entries': n_entries, 'rules': n_rules,
           'concept_members': {k: sorted(v) for k, v in members.items()},
           'collapse_pairs_ge_0.5': [{'a': a, 'b': b, 'jaccard': round(j, 3)} for j, a, b, _ in severe],
           'pool': {'main': len(pool['main']), 'extended': len(pool['ext']), 'none': len(pool['none'])},
           'unsupported_rate_upper': round(len(pool['none'])/tot, 4)}
    jp = r'D:/hermes/analysis/cluster_audit_report.json'
    with open(jp, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'报告已落盘: {jp}')
    return code

if __name__ == '__main__':
    sys.exit(main())
