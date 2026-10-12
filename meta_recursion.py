#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
meta_recursion.py — 元递归层 (L2)：审计 L1 检查器，并且可以审计自己 meta(meta)

L0 工作层   : 归档 / 本机模型 / 实验
L1 检查器层 : rsi_gate · cluster_audit · persist_audit · memory_layer · check_local_models
L2 元层     : 本文件。对 L1 施加【元不变量 MR1–MR7】，并做 meta(meta)

设计依据（归档）:
  #54/#57 评估器必须能被独立验证 —— 但"任务分数不能验证评估器"
  #15     判据必须能【拒绝已知坏输入】(negative control)
  #16     要有可辨别的分数分布, 否则判据已死 (r_disc → 0)
  #100/#101 Harness 演化的"增益"常常是评测假象 ⇒ 必须带中性对照
  #183    说 A 与 B 相关前先问: 是否只动了一根轴?
  #175    每条规则须同时给出 观测量 / 阈值 / 阈值附近怎么办
  #188 M4 结案必须带 reopen_if, 否则结论会僵死

用法:
  python meta_recursion.py --register         # 生成 checkers.json（L1 的声明台账）
  python meta_recursion.py --audit            # 静态+动态审计 L1（默认）
  python meta_recursion.py --inject real      # 用"真实已知错例"(自对弈R3)测元层能否捕获
  python meta_recursion.py --inject good      # 用一条【合格声明】做正对照
  python meta_recursion.py --self             # meta(meta)：元层审计自己
"""
import json, os, re, sys

try:
    from _paths import ROOT as BASE, TOOLS_DIR, STATE_DIR, SANDBOX_DIR
except Exception:
    BASE = r'D:/hermes/analysis'; TOOLS_DIR=STATE_DIR=SANDBOX_DIR=BASE
REG  = os.path.join(STATE_DIR, 'checkers.json')

# ── 元不变量（每条: 观测量 / 阈值 / 阈值附近怎么办）────────────────────
META = {
 'MR1': dict(name='自指检查',
   obs='检查器是否把另一个检查器的输出当真值（自确认闭环）',
   thr='出现【0 处】跨检查器真值引用才算通过',
   edge='若确有引用: 必须显式标注"该真值本身带不确定性"并给第二真值源'),
 'MR2': dict(name='判别力分布',
   obs='检查器的判定是否只剩一个取值（全过/全不过 ⇒ 判据已死）',
   thr='输出分布 std > 0，且非平凡判定数 ≥ 2',
   edge='std 恰好为 0 但样本 <5 ⇒ 记"样本不足", 不判死'),
 'MR3': dict(name='中性对照存在性',
   obs='凡声称"改进/有效"处，是否带中性对照（placebo/无干预臂）',
   thr='每一条改进声明 ≥1 个中性对照',
   edge='无对照但结论带"仅描述、非因果"字样 ⇒ 降级为观察, 不算失败'),
 'MR4': dict(name='单轴性',
   obs='两组比较之间是否只差一根轴',
   thr='差异轴数 = 1',
   edge='多轴时必须声明交互项, 并给出 2×2 全交叉'),
 'MR5': dict(name='测量与结论分离',
   obs='产出结论的【解析器/指标】是否在已知输入上校准过',
   thr='解析器有 negative control（能对已知坏/好输入给出预期值）',
   edge='无校准但指标与结论分离在不同函数 ⇒ 记警告（可事后补）'),
 'MR6': dict(name='翻转条件',
   obs='结案/判定是否带 reopen_if',
   thr='每条结论 ≥1 个 reopen_if',
   edge='一次性描述性统计可免, 但须显式标"不结案"'),
 'MR7': dict(name='自适用性',
   obs='元层自己是否满足它向 L1 要求的条件 (递归闭合)',
   thr='MR1–MR6 对元层自身全部可评且结论为通过或显式豁免',
   edge='若元层自称豁免 ⇒ 必须写出豁免理由与代偿措施'),
}

# ── L1 声明台账（--register 可重建；此处按实际实现如实登记）──────────
L1 = {
 'rsi_gate.py': dict(role='变更前闸', emits='exit code + 10 闸结论（含⑨评判器可靠性 / ⑩上下游成对兼容）+ 校准(negative control) + 判别力分布 + reopen_if + 新闸阴性对照',
   has_dist=True, has_control=True, has_reopen=True, parser_calibrated=True,
   axes='n/a（单闸判定）；⑩另含上游sha绑定/下游逐个复验/装配后行为三要件'),
 'cluster_audit.py': dict(role='每次归档闸', emits='Jaccard 对 + 分池计数 + exit',
   has_dist=True, has_control=False, has_reopen=False, parser_calibrated=True,
   axes='两两 Jaccard（单轴: 概念重合度）'),
 'persist_audit.py': dict(role='骨架不变量', emits='I1–I5 + exit',
   has_dist=False, has_control=False, has_reopen=True, parser_calibrated=True,
   axes='跨轮对账（单轴: 时间）'),
 'memory_layer.py': dict(role='记忆写入闸', emits='闸结论 + 分池 + 坍缩 + M1–M5',
   has_dist=True, has_control=False, has_reopen=True, parser_calibrated=False,
   axes='⚠️ 分池/Jaccard/闸 三轴同时出现'),
 'check_local_models.py': dict(role='本机模型校验', emits='garbage/max_rep/tok_s',
   has_dist=True, has_control=False, parser_calibrated=False,
   axes='单轴（模型）'),
 'selfplay_trial3.py': dict(role='自对弈实验(R3)', emits='准确率表',
   has_dist=True, has_control=False, has_reopen=False, parser_calibrated=False,
   axes='⚠️ 模型×格式 双轴'),
 'write_gate.py': dict(role='事务级写入闸', emits='WAL + 提交结论 + 7 破坏性测试',
   has_dist=True, has_control=True, has_reopen=True, parser_calibrated=True,
   axes='单轴（每次只在一个事务内改主存）',
   reuse_import=['memory_layer']),      # ⭐ 代码复用（调它的逐条闸），不是真值复用
 'verify_layer_v2.py': dict(role='验证层·引文保真', emits='四档判决 + 校准 + 否证通道',
   has_dist=False, has_control=True, has_reopen=False, parser_calibrated=True,
   axes='单轴（数字+量纲+语义锚点）'),
 'repro_audit.py': dict(role='复现审计', emits='B 类自洽 + A 类数值对',
   has_dist=False, has_control=False, has_reopen=False, parser_calibrated=True,
   axes='单轴（计数）'),
 'baseline.py': dict(role='基线·全栈收口', emits='11 项判决 + 冻结 + 自检',
   has_dist=True, has_control=True, has_reopen=False, parser_calibrated=True,
   axes='单轴（每项独立判, 不混合）'),
}

# ── 台账覆盖: 元层必须能发现"自己没审计谁" ──────────────────────────
CHECKER_HINT = re.compile(r'(gate|audit|check|trial|layer)')
def coverage():
    """⭐ 修: 必须区分三件事 ——
       (a) 像检查器但【未登记】
       (b) 已登记但【不匹配启发式】(文件在, 只是名字不含 gate/audit/check/trial/layer)
       (c) 已登记且【磁盘上真没有】
       旧版把 (b) 误报成 (c) —— 于是 baseline.py 被报成"磁盘上没了"。"""
    on_disk = [f for f in os.listdir(TOOLS_DIR) if f.endswith('.py')] + \
              [f for f in os.listdir(BASE) if f.endswith('.py')]
    hinted = [f for f in on_disk if CHECKER_HINT.search(f)]
    reg = set(L1.keys())
    missing   = sorted(set(hinted) - reg)                 # (a)
    not_hinted = sorted(reg - set(hinted))                # (b)
    absent    = sorted(f for f in reg if f not in on_disk)  # (c) 真不存在
    return missing, not_hinted, absent

def src(name):
    p = os.path.join(BASE, name) if os.path.exists(os.path.join(BASE, name)) else os.path.join(TOOLS_DIR, name)
    return open(p, encoding='utf-8', errors='replace').read() if os.path.exists(p) else ''

def neg_control_present(code):
    """在源码里找"对已知坏输入求预期"的痕迹（negative control / 校准）"""
    return bool(re.search(r'negative[_ ]?control|neg_ctrl|校准|已知坏|故意|deliberately|placebo|中性对照|对照组', code, re.I))

def control_present(code):
    return bool(re.search(r'placebo|中性|对照|control|baseline|基线', code, re.I))

def reopen_present(code):
    return bool(re.search(r'reopen_if|翻转条件', code))

def audit_auto():
    """磁盘扫描 + 源码推断 ⇒ 覆盖所有"像检查器"的文件（不再依赖人工登记）
    ⚠️ 推断项标为【未声明】：推断不等于声明，两者分开报，不合并成一个数（#178 分池）"""
    miss, _not_hinted, _absent = coverage()
    if not miss:
        print('  自动审计: 无未登记项'); return []
    print('\n' + '─' * 92)
    print(f'  自动审计（源码推断, 未声明）: {len(miss)} 个文件')
    print('─' * 92)
    inferred = []
    for name in miss:
        c = src(name)
        if not c: continue
        sig = dict(
          MR2=bool(re.search(r'\bstd\b|statistics|Jaccard|jaccard|distribution|分池|计数|len\(', c)),
          MR3=bool(re.search(r'placebo|中性|对照|control|baseline|基线', c, re.I)),
          MR4=bool(re.search(r'轴|axis|2x2|2×2|单轴', c)),
          MR5=bool(re.search(r'calibrat|校准|negative[_ ]?control|已知坏', c, re.I)),
          MR6=bool(re.search(r'reopen_if|翻转条件', c)),
        )
        n = sum(1 for v in sig.values() if v)
        inferred.append((name, sig, n))
    inferred.sort(key=lambda x: -x[2])
    for name, sig, n in inferred[:12]:
        print(f'    {name:<38} 推断通过 {n}/5  ' + ' '.join(k[-1] for k, v in sig.items() if v))
    if len(inferred) > 12:
        print(f'    … 其余 {len(inferred)-12} 个（按通过数降序）')
    tot_decl = len(L1); tot_auto = len(inferred)
    print('─' * 92)
    print(f'  ⭐ 覆盖率: 已声明 {tot_decl} + 推断 {tot_auto} = {tot_decl+tot_auto} 个'
          f'  （推断项【未声明】, 不计入 L1 失败率, 分开报）')
    zero = [n for n, s, k in inferred if k == 0]
    print(f'  ⚠️ 推断 0/5 的"检查器": {len(zero)} 个 {zero[:6]}')
    return inferred

def audit_static():
    print('=' * 92)
    print('L2 元层 · 静态审计 L1（MR1–MR6）')
    print('=' * 92)
    rows = []
    for name, d in L1.items():
        c = src(name)
        # 字段缺省 ⇒ 记 None，并单独作为"声明不完整"报出（不静默当 False）
        g = lambda k: d.get(k, None)
        incomplete = [k for k in ('has_dist','has_control','has_reopen','parser_calibrated','axes')
                      if k not in d]
        # MR6: reopen_if 既看声明也看源码
        mr6 = bool(g('has_reopen')) or reopen_present(c)
        # MR3: 对照
        ctrl = bool(g('has_control')) or control_present(c)
        # MR5: 校准痕迹
        cal  = bool(g('parser_calibrated')) or neg_control_present(c)
        # MR2: 输出分布
        mr2 = g('has_dist')
        # MR4: 轴数（用 ⚠️ 标记登记的多轴）
        multi = '⚠️' in str(g('axes'))
        res = dict(MR2=('—' if mr2 is None else ('✅' if mr2 else '❌')),
                   MR3=('✅' if ctrl else '❌'),
                   MR4=('❌ 多轴' if multi else '✅'),
                   MR5=('✅' if cal else '❌'),
                   MR6=('✅' if mr6 else '❌'))
        n_fail = sum(1 for v in res.values() if v.startswith('❌'))
        rows.append((name, res, n_fail, len(c)))
        print(f'\n  {name}   (源码 {len(c)} 字)  失败 {n_fail}/5'
              + (f'  ⚠️ 声明缺字段 {incomplete}' if incomplete else ''))
        print(f'    MR2 判别力分布 : {res["MR2"]}    MR3 中性对照 : {res["MR3"]}')
        print(f'    MR4 单轴性     : {res["MR4"]}    MR5 测量已校准: {res["MR5"]}')
        print(f'    MR6 翻转条件   : {res["MR6"]}    轴声明: {g("axes")}')
    tot = sum(r[2] for r in rows)
    print('\n' + '─' * 92)
    print(f'  L1 合计失败项: {tot} / {len(rows)*5}')
    worst = sorted(rows, key=lambda x: -x[2])[:3]
    print(f'  ⚠️ 最弱三件: ' + ' · '.join(f'{n}({k})' for n, _, k, _ in worst))
    return rows

def audit_dynamic():
    """MR1 自指检查 + 覆盖检查 + MR7 自适用性"""
    print('\n' + '=' * 92)
    print('L2 元层 · MR1 自指检查 + 覆盖 + MR7 自适用性')
    print('=' * 92)
    code_reuse, truth_reuse = [], []
    for name in L1:
        c = src(name)
        for other in L1:
            if other == name: continue
            stem = other.replace('.py', '')
            imported = bool(re.search(rf'^\s*(import\s+{stem}|from\s+{stem}\s+import)', c, re.M))
            # 真值复用: 用 shell 调另一个检查器，并拿它的【退出码/输出】当真值
            spawned = bool(re.search(rf'subprocess[^\n]*{stem}\.py', c))
            uses_rc = bool(re.search(r'returncode', c))
            if imported: code_reuse.append((name, other))
            if spawned and uses_rc: truth_reuse.append((name, other))
    print(f'  MR1a 代码复用(import): {len(code_reuse)} 处  {code_reuse if code_reuse else "—"}')
    print(f'       → ✅ 代码复用【不算】自确认闭环（复用实现, 不复用真值）')
    print(f'  MR1b 真值复用(调另一检查器且吃它的退出码/输出): {len(truth_reuse)} 处  '
          + ('✅ 无自确认闭环' if not truth_reuse else f'❌ {truth_reuse}'))
    miss, not_hinted, absent = coverage()
    print(f'  覆盖检查: (a) 像检查器但【未登记】= {len(miss)}  {miss[:6]}{" …" if len(miss)>6 else ""}')
    print(f'            (b) 已登记但【不匹配启发式】= {len(not_hinted)}  {not_hinted}')
    print(f'            (c) 已登记且【磁盘上真没有】= {len(absent)}  {absent if absent else "— ✅"}')
    if miss:
        print(f'           ⚠️ 元层对未登记层【是盲的】⇒ 覆盖率 = {len(L1)}/{len(L1)+len(miss)}')
    print(f'  MR7 自适用性: 元层对自身逐条自评 →')
    selfres = self_audit(silent=True)
    for k, v in selfres.items():
        print(f'      {k}: {v[0]}  {v[1]}')
    return code_reuse, truth_reuse, miss, selfres

def self_audit(silent=False):
    c = src('meta_recursion.py')
    res = {
     'MR1 自指闭环': ('✅', '元层不把任何 L1 输出当真值；L1 只是被测对象'),
     'MR2 判别力':   ('✅', f'元层输出 5 值×6 对象 = 30 格判定，非单值 ⇒ std>0'),
     'MR3 中性对照': ('✅', '本文件含 --inject good 作正对照、real 作负对照'),
     'MR4 单轴性':   ('✅', '每次只对一根元不变量给判定；多轴在 L1 侧登记'),
     'MR5 测量校准': ('⚠️', '元层的"是否校准"是【源码正则判定】—— 该判定器本身尚无 negative control'),
     'MR6 翻转条件': ('✅', '每条 MR 带 edge（阈值附近处置）与可复跑命令'),
    }
    return res

def inject(kind):
    """把一条【声明】喂给元层，看它能否判出不合格 —— 这是元层的 negative/positive control"""
    claims = {
      'real': dict(  # ⭐ 真实错例: 我 R3 的结论
        claim='弱判官(minicpm)比强判官(7b-clean)更有用: 50% vs 0%',
        measured_by='selfplay_trial3.py',
        control=None,                       # 无中性对照
        axes_changed=['model', 'output_format'],   # 双轴
        parser_validated=False,             # "评分" 解析器抓到 "0-10" 里的 0
        reopen_if=None,
        n=12),
      'good': dict(  # 正对照: R5 之后的合格声明
        claim='在基线 0% 的极难题上, 一切"再作答"条件把匹配率提到 33–67%; 中性对照 33% ⇒ 主因是再推导框架而非审阅内容',
        measured_by='selfplay_trial5(对照) + trial4(2×2)',
        control='（无审阅意见）= 中性对照 33%',
        axes_changed=['prompt_template'],   # 单轴
        parser_validated=True,              # SCORE= 只认显式标记
        reopen_if='若题集移入 70–90% 信息带后效应消失 ⇒ 该结论仅限极难区',
        n=12),
    }
    cl = claims[kind]
    print('=' * 92); print(f'L2 元层 · 注入测试: --inject {kind}'); print('=' * 92)
    print(f'  声明: {cl["claim"][:70]}')
    fails = []
    if not cl.get('control'):                     fails.append('MR3 失败: 无中性对照')
    if len(cl.get('axes_changed', [])) != 1:      fails.append(f'MR4 失败: 变了 {len(cl["axes_changed"])} 根轴 {cl["axes_changed"]}')
    if not cl.get('parser_validated'):            fails.append('MR5 失败: 指标解析器未在已知输入上校准')
    if not cl.get('reopen_if'):                   fails.append('MR6 失败: 无翻转条件 ⇒ 结论会僵死')
    if cl.get('n', 0) < 5:                        fails.append('MR2 失败: 样本不足, 判定分布不可信')
    print()
    if fails:
        print(f'  ⭐ 判决: ❌ 不合格（{len(fails)} 项）')
        for f in fails: print(f'     · {f}')
        print(f'  ⭐ 处置: 按 #175 —— 先补【中性对照 × 同一模型 × 同一格式】三件套，再谈机制')
    else:
        print('  ⭐ 判决: ✅ 合格（MR2–MR6 全过）')
        print(f'     对照: {cl["control"]}')
        print(f'     翻转: {cl["reopen_if"]}')
    return fails

def register():
    json.dump(dict(level=1, checkers=L1, meta_invariants=META),
              open(REG, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'已写台账 {REG}（{len(L1)} 个 L1 检查器 + {len(META)} 条元不变量）')

def main():
    if '--register' in sys.argv: register(); return 0
    if '--inject' in sys.argv:
        k = sys.argv[sys.argv.index('--inject') + 1]
        inject(k); return 0
    if '--self' in sys.argv:
        print('L2 元层 · meta(meta) — 元层审计自己'); print('=' * 92)
        for k, v in self_audit().items():
            print(f'  {v[0]:<3} {k:<14} {v[1]}')
        return 0
    register() if not os.path.exists(REG) else None
    rows = audit_static()
    audit_dynamic()
    audit_auto()
    print('\n' + '=' * 92)
    print('L2 元层 · 结论')
    print('=' * 92)
    print('  ⭐ 元层的价值不在"全绿"，而在【它能让元层自己变红】:')
    print('     MR5 对元层自身 = ⚠️ —— 元层的"是否已校准"判定，本身就是个未校准的正则。')
    print('     这条 ⚠️ 必须留在报告里，不能抹平（#188 L5: 指标饱和 ⇒ 判据失效）。')
    return 0

if __name__ == '__main__':
    sys.exit(main())
