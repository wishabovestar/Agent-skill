#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
persist_audit.py — 持久系统的演化 · 不变量检查器（纯 stdlib，只读归档，幂等）

为什么需要它：本归档与本 Agent 集群是【持久系统】—— 跨会话、跨上下文压缩、跨版本存活。
归档自己已经证明这类系统会【悄悄退化】：
  #124  compaction summary 被实测为【失准载体】（状态层即传导层）
  #78   指标饱和 ⇒ 判据失效 ⇒ 你不知道自己达没达标
  #113  harness 扩张本身造成遗忘（agent 轴 −34.7%）
  #104/#105/#106  越训越窄 / 熵坍缩 / 收窄发生在【入口】
  #9    总有一层不可演化（可演化部分必须挂在不可变骨架上）
⇒ 因此需要一个「骨架不变量」的机器检查：**每次运行都能回答"这一轮有没有把我拖坏"**。

不变量（I1–I5）：
  I1 编号连续        —— 断裂 = 结构性损坏（不可原谅）
  I2 条目数单调不减  —— 归档只增（#4 非破坏、可增量）
  I3 铁律数单调不减  —— 同上
  I4 已结案不被重开  —— 结案台账必须持久（否则悬案永远悬着）
  I5 概念成员突变率  —— 某概念成员数相对上次变化过大 ⇒ 可能是【混用/词表漂移】信号

用法：
  python persist_audit.py            # 首次=建快照；再次=对账
  python persist_audit.py --reset    # 重建快照（会丢掉历史对账基线，慎用）
"""
import re, sys, os, json, hashlib

ARCHIVE  = r'D:/hermes/analysis/PAPER_ARCHIVE_agent_memory_swarm_2026-10.md'
SNAP     = r'D:/hermes/analysis/persist_snapshot.json'
LEDGER   = r'D:/hermes/analysis/persist_ledger.json'   # 结案台账（持久，人工/脚本维护）
MUTATE_WARN = 0.30   # I5 阈值：成员数变化 >30% ⇒ 警告（可调，但须【记录改过】）

CONCEPTS = {
    '解耦': r'解耦|DECOUPL|decoupl|正交分解',
    '分工': r'分工|各用其长|各管一件事|各有一处短',
    '校准失效': r'校准(?:在|失效)|calibration|分布一变',
    '条件边界': r'边界条件|报条件|boundary condition|regime|适用条件',
    '反驳通道': r'反驳|refutation|否证|被违反着试|可被检验',
    '两池': r'两池|主池|扩展池|可比与覆盖',
    'bi-level': r'bi-level|个体级|条件在.*两层',
    '事后贴名': r'事后贴|post-?hoc|名字.*事后|可辨识.*可解释',
    '元求解器': r'元求解器|meta-solver',
    '置换不变': r'置换不变|permutation-invariant',
    '单轴': r'单轴|single-axis|一次只动|只变一个',
    '误差分解': r'误差.*分解|隔离.*误差|isolates.*error',
    '下界': r'下界|lower bound|不可约',
    '探针': r'探针|probe|最弱读出器|诊断任务',
    '人工先定': r'手工汇总|人工预定|人工标注|手工贴|hand-?crafted|manually',
}

# 默认结案台账（首次运行写入；之后由脚本/人追加，不许静默删除）
DEFAULT_LEDGER = {
    'closed': [
        {'id': 'C1', 'case': '解耦 × 分工 是否同一概念',
         'verdict': '非坍缩 (Jaccard=0.146, 共有 7 条)',
         'scope': '仅对 2026-10-11 的 186 条成立', 'reopen_if': 'Jaccard ≥ 0.30'},
    ],
    'reopened': []
}

def sha_short(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:16]

def load_archive():
    with open(ARCHIVE, encoding='utf-8') as f:
        return f.read()

def fingerprint(t):
    nums = [int(x) for x in re.findall(r'^### (\d+)\.', t, re.M)]
    m = re.search(r'^## 跨论文铁律.*?\n(.*?)^---', t, re.M | re.S)
    rules = [int(x) for x in re.findall(r'^(\d{1,3})\.\s', m.group(1), re.M)] if m else []
    # 概念成员（只取大小 + 成员列表的哈希，避免快照过大）
    members = {}
    blocks = re.split(r'^### ', t, flags=re.M)[1:]
    ent = {}
    for b in blocks:
        mm = re.match(r'(\d+)\.', b)
        if mm: ent[int(mm.group(1))] = b
    for name, pat in CONCEPTS.items():
        rx = re.compile(pat, re.I)
        members[name] = sorted(n for n, b in ent.items() if rx.search(b))
    return {
        'n_entries': len(nums), 'nums_contiguous': nums == list(range(1, len(nums) + 1)),
        'last_num': nums[-1] if nums else 0,
        'n_rules': len(rules), 'rules_contiguous': rules == list(range(1, len(rules) + 1)),
        'kb': os.path.getsize(ARCHIVE) // 1024,
        'lines': t.count('\n') + 1,
        'n_concepts': len(members),
        'concept_sizes': {k: len(v) for k, v in members.items()},
        'concept_sets_hash': {k: sha_short(','.join(map(str, v))) for k, v in members.items()},
        'concept_members': members,
    }

def main():
    reset = '--reset' in sys.argv
    t = load_archive()
    cur = fingerprint(t)

    print('=' * 78)
    print('persist_audit.py — 持久系统的演化 · 不变量检查')
    print('=' * 78)
    print(f'归档: {ARCHIVE}')
    print(f'当前: {cur["n_entries"]} 条 / 铁律 {cur["n_rules"]} / {cur["kb"]} KB / {cur["lines"]} 行')

    # 结案台账
    if not os.path.exists(LEDGER) or reset:
        with open(LEDGER, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_LEDGER, f, ensure_ascii=False, indent=2)
        print(f'结案台账: 已初始化 → {LEDGER}')
    ledger = json.load(open(LEDGER, encoding='utf-8'))
    print(f'结案台账: {len(ledger["closed"])} 条已结案 / {len(ledger["reopened"])} 条被重开')

    # 无快照 ⇒ 建立基线
    if not os.path.exists(SNAP) or reset:
        with open(SNAP, 'w', encoding='utf-8') as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
        print()
        print('⭐ 无历史快照 ⇒ 本轮建立【基线】。下次运行将对账（持久性的关键在第二次）。')
        print(f'   快照 → {SNAP}')
        print('=' * 78)
        return 0

    prev = json.load(open(SNAP, encoding='utf-8'))
    problems, warnings, news = [], [], []

    # ── I1 编号连续 ─────────────────────────────────────────────────────
    if not cur['nums_contiguous']:
        problems.append('I1 编号【断裂】⇒ 结构性损坏（归档本该只增不改）')
    else:
        print('  I1 编号连续           ✅')

    # ── I2 / I3 单调不减 ────────────────────────────────────────────────
    d_e = cur['n_entries'] - prev['n_entries']
    d_r = cur['n_rules'] - prev['n_rules']
    if d_e < 0: problems.append(f'I2 条目数【减少】{prev["n_entries"]}→{cur["n_entries"]}')
    else: print(f'  I2 条目数单调不减      ✅  {prev["n_entries"]} → {cur["n_entries"]}  (+{d_e})')
    if d_r < 0: problems.append(f'I3 铁律数【减少】{prev["n_rules"]}→{cur["n_rules"]}')
    else: print(f'  I3 铁律数单调不减      ✅  {prev["n_rules"]} → {cur["n_rules"]}  (+{d_r})')

    # ── I4 已结案不被重开 ───────────────────────────────────────────────
    reopened = []
    pm = prev.get('concept_sizes', {})
    for c in ledger['closed']:
        if c.get('case', '').startswith('解耦') and '≥ 0.30' in c.get('reopen_if', ''):
            # 重算 Jaccard（只对 |集合|≥3 的对）
            a, b = cur['concept_members'].get('解耦', []), cur['concept_members'].get('分工', [])
            if len(a) >= 3 and len(b) >= 3:
                j = len(set(a) & set(b)) / len(set(a) | set(b))
                if j >= 0.30:
                    reopened.append(f'I4 结案 {c["id"]}（{c["case"]}）触发重开条件: J={j:.3f} ≥ 0.30')
                else:
                    print(f'  I4 结案 {c["id"]} 未被重开   ✅  J={j:.3f} < 0.30')
    if reopened: problems += reopened

    # ── I5 概念成员突变率 ───────────────────────────────────────────────
    print('  I5 概念成员突变率（>%.0f%% ⇒ 混用/词表漂移信号）' % (MUTATE_WARN * 100))
    for k in CONCEPTS:
        p, c = pm.get(k, 0), cur['concept_sizes'].get(k, 0)
        if p == 0:
            if c: news.append(f'I5 新概念进入视野: {k} ({c} 条)')
            continue
        rate = abs(c - p) / p
        if rate > MUTATE_WARN:
            warnings.append(f'I5 「{k}」成员数突变 {p}→{c} ({rate:+.0%})')

    # ── 报 ──────────────────────────────────────────────────────────────
    print()
    print('── 变化' + '─' * 70)
    print(f'  KB {prev["kb"]} → {cur["kb"]}   |   行 {prev["lines"]} → {cur["lines"]}')
    if news:
        for n in news: print(f'  · {n}')
    if warnings:
        print('  ⚠️ 警告:')
        for w in warnings: print(f'    · {w}')
    if not warnings and not news:
        print('  （无显著变化）')

    print()
    print('── 结论' + '─' * 70)
    if problems:
        print('  ❌ 不变量被破坏:')
        for p in problems: print(f'    · {p}')
        print('  ⇒ 先修复损坏，再继续演化（#9：骨架不可动）')
        code = 1
    else:
        print('  ✅ 全部骨架不变量保持 ⇒ 本轮演化【没有把系统拖坏】')
        if warnings: print('  ⚠️ 但有警告项（可接受，需记录）')
        code = 0
    print('=' * 78)

    # 本轮对账完成后推进快照（保留"上一次"用于下一次对账）
    with open(SNAP, 'w', encoding='utf-8') as f:
        json.dump(cur, f, ensure_ascii=False, indent=2)
    return code

if __name__ == '__main__':
    sys.exit(main())
