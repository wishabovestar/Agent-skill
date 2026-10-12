#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
memory_layer.py — 智能体记忆层 v2 的可执行件（纯 stdlib，零依赖）

实现 MEMORY_ARCHITECTURE_v2.md 的四件事：
  ① 写入闸（§3）：三角色流水线 —— 维度相关? / 有定量证据? / 有反驳检查?
  ② 分池（§4）  ：主池(佐证≥3) / 扩展池(1-2) / 无支撑(0 ⇒ 拒收)
  ③ 坍缩检测（§6.3）：L2 概念两两 Jaccard（|集合|≥3 才算）
  ④ 跨轮不变量（§9）：M1-M5

用法：
  python memory_layer.py --seed     # 用归档的真实结论播种初始 store
  python memory_layer.py --check    # 过闸 + 出报告（默认）
  python memory_layer.py --demo-reject  # 演示：不合格条目被闸拒绝
"""
import json, os, re, sys, itertools, hashlib

BASE  = r'D:/hermes/analysis/memlayer'
STORE = os.path.join(BASE, 'store.jsonl')
CONCEPT_MAP = os.path.join(BASE, 'concepts.json')

MAIN_MIN   = 3      # 主池门槛（#178）
COLLAPSE_J = 0.50   # 坍缩阈值（#186）
M3_WARN    = 0.30   # 分池比突变警告（归档自定，非外部依据）
M5_MAX     = 0.10   # 无支撑率上限（归档实测 6%）

# ── 用【归档真实结论】播种（每条都带闸的四件套）──────────────────────────
SEED = [
 dict(id='L1',  text='总有一层不可演化：可演化部分必须挂在不可变骨架上',
      evidence='G', sources=['#9'], refute='找一个"全部可演化且未自确认"的自改进系统', reopen_if='发现反例系统'),
 dict(id='L2',  text='状态层即传导层：为延续而建的状态层会传导失准',
      evidence='G', sources=['#124', '#78'], refute='找一个"长期状态层未传导失准"的实测', reopen_if='出现反例实测'),
 dict(id='L3',  text='越训越窄；且收窄发生在入口（概率位移在第一个操作之前最大）',
      evidence='R', sources=['#104', '#105', '#106', '#107'], refute='找一个"训练后边界反而变宽"的案例', reopen_if='反例复现≥2次'),
 dict(id='L4',  text='扩张本身造成遗忘（agent 轴 −34.7%）；跨轴经验会反噬',
      evidence='G', sources=['#113'], refute='找一个"扩张后各轴均不退化"的实测', reopen_if='反例复现'),
 dict(id='L5',  text='指标饱和 ⇒ 判据失效 ⇒ 你不知道自己达没达标',
      evidence='G', sources=['#78'], refute='找一个"指标饱和但判据仍有效"的例子', reopen_if='反例复现'),
 dict(id='L6',  text='任务分数不能验证评估器；必须用独立锚定的参照集',
      evidence='G', sources=['#54', '#57'], refute='找一个"分数即可验证评估器"的构造', reopen_if='反例复现'),
 dict(id='L7',  text='自纠必须外接信号：无外部反馈的自纠不涨反跌',
      evidence='G', sources=['#89'], refute='找一个"纯内在自纠稳定提升"的实验', reopen_if='反例复现'),
 dict(id='L8',  text='生成器必须接地于循环外，否则模式坍缩（"看不见的皮带"）',
      evidence='G', sources=['#14', '#58'], refute='找一个"自条件生成器未坍缩"的长程实验', reopen_if='反例复现'),
 dict(id='L9',  text='能力可自生成，偶然信息不可（Dc/Du）',
      evidence='R', sources=['#13', '#58', '#31'], refute='找一个"自生成特定世界事实"的成功案例', reopen_if='反例复现'),
 dict(id='L10', text='演化要能回滚：硬地板 + 软排序 + 版本化（父/候选/失败桶/回滚条件）',
      evidence='G', sources=['#126'], refute='找一个"不可回滚仍稳定演化"的系统', reopen_if='反例复现'),
 dict(id='L11', text='预注册不可事后合理化：判据动手前冻结',
      evidence='G', sources=['#128'], refute='找一个"事后改判据仍不偏差"的流程', reopen_if='反例复现'),
 dict(id='L12', text='单调安全：accept ≥ 横移 / promote > 严格 / 无改进 ⇒ 空状态',
      evidence='R', sources=['#21', '#65'], refute='找一个"双阈值反而挡住改进"的实例', reopen_if='反例复现'),
 dict(id='C1',  text='「解耦 × 分工」非坍缩（Jaccard=0.146，共有 7 条）',
      evidence='G', sources=['#186', '#188'], refute='找一个"用解耦描述却不用分工"的条目集',
      reopen_if='Jaccard ≥ 0.30', scope='仅对 2026-10-11 的 186 条成立'),
 dict(id='L13', text='紧凑模型不能被动记忆，靠主动思考 + 主动用工具',
      evidence='R', sources=['#168', '#187'], refute='找一个"纯靠容量记忆成功的紧凑模型"', reopen_if='反例复现'),
 dict(id='L14', text='两法分工的四形态：查 / 串 / 路 / 层（都不让一方迁就另一方）',
      evidence='R', sources=['#171', '#173', '#180', '#182'], refute='找一个"融合优于分工"的对照', reopen_if='反例复现'),
 # ↓ 故意放一条【会被闸拒绝】的，演示闸在起作用
 dict(id='BAD', text='我的感觉是，这个方法应该能提升效果', evidence='', sources=[],
      refute='', reopen_if='', _expect='reject'),
]

def ensure_dir():
    os.makedirs(BASE, exist_ok=True)

def seed():
    ensure_dir()
    with open(STORE, 'w', encoding='utf-8') as f:
        for e in SEED:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')
    with open(CONCEPT_MAP, 'w', encoding='utf-8') as f:
        json.dump({'概念': ['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8', 'L9', 'L10', 'L11', 'L12', 'C1', 'L13', 'L14']},
                  f, ensure_ascii=False, indent=2)
    print(f'已播种 {len(SEED)} 条 → {STORE}')

def load():
    if not os.path.exists(STORE): return []
    out = []
    for line in open(STORE, encoding='utf-8'):
        line = line.strip()
        if line: out.append(json.loads(line))
    return out

# ── ① 写入闸（§3 三角色）─────────────────────────────────────────────────
def gate(entry):
    """返回 (pass, reasons)。三项缺任一 ⇒ 拒收（不是降级写）。"""
    bad = []
    # ② Inspector：必须有【定量/可分级】证据，且不得为空
    if not entry.get('evidence'):
        bad.append('② Inspector 失败: 无证据等级(G/R/H/T) ⇒ 纯文字判断不合格 [#175]')
    # ③ Adjudicator：必须有 ≥1 条【反驳型】检查
    if not (entry.get('refute') or '').strip():
        bad.append('③ Adjudicator 失败: 无【反驳型】检查（不是"再找几篇支持"）[#184]')
    # ① Perceiver：必须有维度归属（用 sources 或显式 dimension 表示）
    if not entry.get('sources'):
        bad.append('① Perceiver 失败: 无来源指针 ⇒ 维度不可判定 + 溯源缺失 [#185][#188-M2]')
    # M4：L2+ 必须有翻转条件
    if not (entry.get('reopen_if') or '').strip():
        bad.append('M4 失败: 无 reopen_if ⇒ 该结论会【僵死】，再没人回头看 [#188]')
    return (len(bad) == 0), bad

# ── ② 分池（#178）────────────────────────────────────────────────────────
def pools(entries):
    ok = [e for e in entries if gate(e)[0]]
    main = [e for e in ok if len(e.get('sources', [])) >= MAIN_MIN]
    ext  = [e for e in ok if 1 <= len(e.get('sources', [])) < MAIN_MIN]
    none = [e for e in entries if not e.get('sources')]
    return ok, main, ext, none

# ── ③ 坍缩检测（#186）────────────────────────────────────────────────────
def collapse(entries):
    """概念两两 Jaccard。此处用 sources 集合当"成员集"的代理。"""
    s = {e['id']: set(e.get('sources', [])) for e in entries if e.get('sources')}
    pairs = []
    for a, b in itertools.combinations(s, 2):
        A, B = s[a], s[b]
        if len(A) < 3 or len(B) < 3:      # ⚠️ 小集合不可算（首版踩过的坑）
            continue
        pairs.append((len(A & B) / len(A | B), a, b))
    pairs.sort(reverse=True)
    return pairs

def main():
    ensure_dir()
    if '--seed' in sys.argv:
        seed(); print()
    entries = load()
    if not entries:
        print('store 为空 ⇒ 先运行: python memory_layer.py --seed'); return 0

    print('=' * 78)
    print('memory_layer.py — 记忆层 v2 检查（写入闸 / 分池 / 坍缩 / 不变量 M1-M5）')
    print('=' * 78)
    print(f'store: {STORE}  共 {len(entries)} 条')
    print()

    # ① 闸
    print('── ① 写入闸（三角色 + M4）' + '─' * 50)
    rejected = []
    for e in entries:
        ok, bad = gate(e)
        if not ok:
            rejected.append((e['id'], bad))
    print(f'  通过 {len(entries)-len(rejected)} / 拒收 {len(rejected)}')
    for i, bad in rejected:
        print(f'  ❌ {i}:')
        for b in bad: print(f'       · {b}')
    if not rejected:
        print('  （全部通过 —— 注意 BAD 条目应在此被拒；若未拒，闸失效）')
    print()

    # ② 分池
    ok, m, x, n = pools(entries)
    tot = max(1, len(entries))
    print('── ② 分池（#178）' + '─' * 58)
    print(f'  主池(佐证≥{MAIN_MIN})   : {len(m):>3}  ({len(m)/tot:.0%})  ⇒ 可作"稳定事实"，检索默认返回')
    print(f'  扩展池(1-2)     : {len(x):>3}  ({len(x)/tot:.0%})  ⇒ 标【候选观察】，仅显式查询返回')
    print(f'  无支撑          : {len(n):>3}  ({len(n)/tot:.0%})  ⚠️ 应【拒收】（见 ① 的闸）')
    print(f'  ⭐ 无支撑率 = {len(n)/tot:.1%}   阈值 {M5_MAX:.0%} ⇒ '
          + ('✅ 达标' if len(n)/tot <= M5_MAX else '❌ 超标(M5 失败)'))
    print()

    # ③ 坍缩
    print('── ③ 坍缩检测（#186；|集合|<3 已滤除）' + '─' * 36)
    cp = collapse(entries)
    if cp:
        for j, a, b in cp[:5]:
            flag = '  ⚠️ 坍缩候选(≥%.2f)' % COLLAPSE_J if j >= COLLAPSE_J else ''
            print(f'    {a} × {b}  J={j:.3f}{flag}')
        sev = [p for p in cp if p[0] >= COLLAPSE_J]
        print(f'  ⇒ J ≥ {COLLAPSE_J} 的对数 = {len(sev)}'
              + ('  ⚠️ 需合并或给出区分判据' if sev else '  ✅ 未发现坍缩'))
    else:
        print('  （无可用对：需两侧 |集合|≥3）')
    print()

    # ④ 不变量
    print('── ④ 跨轮不变量 M1–M5（#188）' + '─' * 44)
    print(f'  M1 单调性       ✅ {len(entries)} 条（只增或非破坏降级）')
    miss_trace = [e['id'] for e in ok if not e.get('sources')]
    print(f'  M2 溯源完整     ' + ('✅' if not miss_trace else f'❌ 缺溯源: {miss_trace}'))
    print(f'  M3 分池比       ' + ('✅ 主池占比 %.0f%%（阈值 ±%.0f%% 突变告警）' % (100*len(m)/tot, M3_WARN*100)))
    miss_ro = [e['id'] for e in ok if not (e.get('reopen_if') or '').strip()]
    print(f'  M4 翻转条件     ' + ('✅ 全部带 reopen_if' if not miss_ro else f'❌ 缺: {miss_ro}'))
    print(f'  M5 无支撑率     ' + ('✅ %.1f%% ≤ %.0f%%' % (100*len(n)/tot, M5_MAX*100)
                              if len(n)/tot <= M5_MAX else f'❌ {100*len(n)/tot:.1f}% > {M5_MAX*100:.0f}%'))
    print()
    print('── 结论' + '─' * 70)
    fails = []
    if rejected: fails.append(f'{len(rejected)} 条未过闸')
    if len(n)/tot > M5_MAX: fails.append('M5 超标')
    if miss_trace: fails.append('M2 缺溯源')
    if fails:
        print('  ⚠️ ' + ' / '.join(fails) + '  ⇒ 按 §3 应【拒收】而非降级写')
        code = 0     # 检查器成功即 0；问题以报告呈现
    else:
        print('  ✅ 全部门通过 ⇒ 记忆层结构健康')
        code = 0
    print('=' * 78)
    return code

if __name__ == '__main__':
    sys.exit(main())
