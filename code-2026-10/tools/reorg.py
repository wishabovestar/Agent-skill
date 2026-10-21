#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reorg.py — 分析目录重组（只重排【本工具栈】, 不动 750 文件的历史堆积）

设计原则（拿本会话的教训换来的）:
  ① 先扫依赖再看移动: 有【外部引用】的一律钉住不动（rsi_gate.py / 论文归档 被 skill 引用）
  ② 先备份再动: 全量备份 → _reorg_backup_<ts>/ ; `--rollback` 一键还原
  ③ 路径集中: 各工具不再硬编码子路径, 统一从 _paths.py 取
  ④ 动完必须验: 九器 exit=0 + 基线无退化 + 元层覆盖变成真数字
  ⑤ dry-run 默认: 不加 --apply 只打印计划

目标结构:
  D:/hermes/analysis/harness/
    README.md
    tools/     ← 检查器/元层/基线（rsi_gate.py 钉住原地）
    docs/      ← 报告与设计文档
    state/     ← 运行态 json（可重建）
    sandbox/   ← wg/ · memlayer/（可删）

用法: python reorg.py [--plan] | --apply | --rollback
"""
import os, sys, json, shutil, re, time, subprocess

ROOT = r'D:/hermes/analysis'
H    = os.path.join(ROOT, 'harness')

TOOLS = ['cluster_audit.py', 'persist_audit.py', 'memory_layer.py', 'meta_recursion.py',
         'write_gate.py', 'repro_audit.py', 'repro_probe.py', 'verify_layer.py',
         'verify_layer_v2.py', 'baseline.py', 'check_local_models.py',
         'selfplay_trial.py', 'selfplay_trial2.py', 'selfplay_trial3.py', 'selfplay_trial4.py']
DOCS  = ['MEMORY_ARCHITECTURE_v2.md', 'MEMORY_ARCHITECTURE_v1.md', 'META_RECURSION_LAYER.md',
         'TX_WRITE_GATE.md', 'REPRO_AUDIT.md', 'VERIFY_LAYER.md', 'BASELINE.md',
         'SELFPLAY_TRIAL_REPORT.md', 'local_models_report.md',
         'AGENT_CLUSTER_UPGRADE_BLUEPRINT_v1.md']
STATE = ['baseline.json', 'anchor_lock.json', 'checkers.json', 'persist_snapshot.json',
         'persist_ledger.json', 'repro_arxiv.json', 'repro_pairs.json', 'verify_layer.json',
         'local_models_report.json', 'selfplay_trial.json', 'selfplay_trial2.json',
         'selfplay_trial3.json', 'selfplay_trial4.json', 'selfplay_trial5.json',
         'cluster_audit_report.json']
SBX   = ['wg', 'memlayer']
PINNED = {'rsi_gate.py': 'skills/research/paper-deepread-archive/SKILL.md 引用',
          'PAPER_ARCHIVE_agent_memory_swarm_2026-10.md': '同上 · 且 4 处 analysis 内引用',
          'AGENT_MEMORY_COORD_DESIGN_CHECKLIST_v1.md': '多处引用 · 体量大',
          'THEMATIC_BRIEF_8papers_2026-10-11.md': '被清单引用'}

def plan():
    print('=' * 96)
    print('重组计划（dry-run；加 --apply 才动作）')
    print('=' * 96)
    def ex(names, sub):
        got = [n for n in names if os.path.exists(os.path.join(ROOT, n))]
        miss = [n for n in names if not os.path.exists(os.path.join(ROOT, n))]
        print(f'\n  harness/{sub}/   ({len(got)} 项' + (f'；缺 {len(miss)}: {miss}' if miss else '') + ')')
        for n in got: print(f'      {n}')
        return got
    n_t = len(ex(TOOLS, 'tools'))
    n_d = len(ex(DOCS, 'docs'))
    n_s = len(ex(STATE, 'state'))
    n_b = len(ex(SBX, 'sandbox'))
    print('\n  ⛔ 钉住不动（外部引用）:')
    for k, v in PINNED.items():
        print(f'      {k:<48} — {v}')
    print(f'\n  小计: 移 {n_t+n_d+n_s+n_b} 项；钉住 {len(PINNED)} 项')
    print('\n  需改路径常量的文件（全在 tools/ 内，改用 _paths.py 统一取值）:')
    for n in TOOLS:
        p = os.path.join(ROOT, n)
        if os.path.exists(p):
            k = len(re.findall(r"BASE\s*=\s*r'D:/hermes/analysis'", open(p, encoding='utf-8', errors='replace').read()))
            print(f'      {n:<26} BASE 硬编码 {k} 处')
    return 0

def backup():
    ts = time.strftime('%Y%m%d_%H%M%S')
    dst = os.path.join(ROOT, f'_reorg_backup_{ts}')
    os.makedirs(dst, exist_ok=True)
    manifest = {}
    for sub, names in (('tools', TOOLS), ('docs', DOCS), ('state', STATE)):
        for n in names:
            p = os.path.join(ROOT, n)
            if os.path.exists(p):
                shutil.copy2(p, os.path.join(dst, n)); manifest[n] = f'{sub}/{n}'
    for n in SBX:
        p = os.path.join(ROOT, n)
        if os.path.isdir(p):
            shutil.copytree(p, os.path.join(dst, n), dirs_exist_ok=True); manifest[n + '/'] = f'sandbox/{n}'
    json.dump(dict(ts=ts, manifest=manifest), open(os.path.join(dst, '_manifest.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print(f'  已备份 {len(manifest)} 项 → {dst}')
    return dst

PATHS_MOD = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_paths.py — 路径集中（重组后唯一真源；各工具从这里取, 不再硬编码）
⚠️ 一律用 *_DIR 后缀: 有些工具自己已有 TOOLS/STATE 之类的同名变量,
   直接导入会【覆盖】它们（baseline.py 的 TOOLS 列表就被覆盖过, 触发自动回滚）。"""
import os
ROOT       = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # D:/hermes/analysis
HARNESS    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))                  # .../harness
TOOLS_DIR  = os.path.join(HARNESS, 'tools')
DOCS_DIR   = os.path.join(HARNESS, 'docs')
STATE_DIR  = os.path.join(HARNESS, 'state')
SANDBOX_DIR= os.path.join(HARNESS, 'sandbox')
# ⛔ 钉住原地（外部 skill 引用）
ARCHIVE    = os.path.join(ROOT, 'PAPER_ARCHIVE_agent_memory_swarm_2026-10.md')
CHECKLIST  = os.path.join(ROOT, 'AGENT_MEMORY_COORD_DESIGN_CHECKLIST_v1.md')
'''

def rewrite(files):
    """工具内路径重写 —— 不只改 BASE, 还要改【语义假设】(同目录找兄弟工具/写 state)"""
    n = 0
    for f in files:
        p = os.path.join(H, 'tools', f)
        if not os.path.exists(p): continue
        t = open(p, encoding='utf-8', errors='replace').read()
        o = t
        # ① 统一取路径（⭐ 用 *_DIR 名, 避免覆盖工具自有的 TOOLS/STATE 变量）
        t = re.sub(r"^BASE\s*=\s*r'D:/hermes/analysis'\s*$",
                   "try:\n    from _paths import ROOT as BASE, TOOLS_DIR, STATE_DIR, SANDBOX_DIR\n"
                   "except Exception:\n    BASE = r'D:/hermes/analysis'; TOOLS_DIR=STATE_DIR=SANDBOX_DIR=BASE",
                   t, count=1, flags=re.M)
        if 'from _paths import' not in t:
            t = t.replace("import os", "import os, sys\nsys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))", 1)
        # ② 沙盒
        t = t.replace("os.path.join(BASE, 'wg'", "os.path.join(SANDBOX_DIR, 'wg'")
        t = t.replace("os.path.join(BASE, 'memlayer'", "os.path.join(SANDBOX_DIR, 'memlayer'")
        # ③ 运行态 json
        for s in STATE:
            t = t.replace(f"os.path.join(BASE, '{s}')", f"os.path.join(STATE_DIR, '{s}')")
        # ④ ⭐ 语义: 兄弟工具在 TOOLS_DIR, 不在 ROOT
        t = t.replace("sys.path.insert(0, BASE)", "sys.path.insert(0, TOOLS_DIR)")
        t = t.replace("os.path.join(BASE, f)", "os.path.join(TOOLS_DIR, f)")
        t = t.replace("os.path.join(BASE, name)", "os.path.join(TOOLS_DIR, name)")
        t = t.replace("cwd=BASE", "cwd=TOOLS_DIR")
        # ⑤ ⭐ 语义: 覆盖扫描/源码读取 应指向 TOOLS_DIR
        t = t.replace("os.listdir(BASE)", "os.listdir(TOOLS_DIR)")
        if t != o:
            open(p, 'w', encoding='utf-8').write(t); n += 1
    return n

def verify():
    """⭐ 重组后必须验。
    ⚠️ 排除 verify_layer.py(v1): 它【设计上】校准失败就 exit 1, 不是回归。"""
    print('\n  验证: 从新位置跑各器')
    skip = {'verify_layer.py'}
    targets = ['rsi_gate.py'] + [x for x in TOOLS if x.endswith('.py') and 'trial' not in x and x not in skip]
    ok, bad = 0, []
    for f in targets:
        cwd = ROOT if f == 'rsi_gate.py' else os.path.join(H, 'tools')
        r = subprocess.run(['python', f], cwd=cwd, capture_output=True, timeout=900)
        if r.returncode == 0: ok += 1
        else:
            bad.append((f, r.returncode, (r.stderr or b'').decode('utf-8', 'replace')[-200:]))
    print(f'     通过 {ok} · 失败 {len(bad)}   (跳过 {skip} —— 它按设计会 exit 1)')
    for f, c, e in bad:
        print(f'     ❌ {f} exit={c}\n        {e.strip()[:180]}')
    return len(bad) == 0

def fixups():
    """⭐ 逐工具的【语义修正】—— 通用重写覆盖不到的地方，必须单独处理"""
    n = 0
    # baseline.py: rsi_gate.py 钉在 ROOT, 其余在 TOOLS_DIR ⇒ 必须按存在性选
    p = os.path.join(H, 'tools', 'baseline.py')
    if os.path.exists(p):
        t = open(p, encoding='utf-8', errors='replace').read()
        t = t.replace("p = os.path.join(TOOLS_DIR, f)",
                      "p = os.path.join(BASE, f) if os.path.exists(os.path.join(BASE, f)) else os.path.join(TOOLS_DIR, f)")
        t = t.replace("cwd=TOOLS_DIR", "cwd=BASE if os.path.exists(os.path.join(BASE, f)) else TOOLS_DIR")
        open(p, 'w', encoding='utf-8').write(t); n += 1
    # meta_recursion.py: L1 台账里 rsi_gate.py 在 ROOT, 其余在 TOOLS_DIR
    p = os.path.join(H, 'tools', 'meta_recursion.py')
    if os.path.exists(p):
        t = open(p, encoding='utf-8', errors='replace').read()
        t = t.replace("p = os.path.join(TOOLS_DIR, name)",
                      "p = os.path.join(BASE, name) if os.path.exists(os.path.join(BASE, name)) else os.path.join(TOOLS_DIR, name)")
        # 覆盖扫描: 台账已登记的钉住项也要算进来
        t = t.replace("on_disk = [f for f in os.listdir(TOOLS_DIR) if f.endswith('.py')]",
                      "on_disk = [f for f in os.listdir(TOOLS_DIR) if f.endswith('.py')] + \\\n"
                      "              [f for f in os.listdir(BASE) if f.endswith('.py')]")
        open(p, 'w', encoding='utf-8').write(t); n += 1
    return n


def apply():
    print('=' * 96); print('重组：应用'); print('=' * 96)
    d = backup()
    for sub in ('tools', 'docs', 'state', 'sandbox'):
        os.makedirs(os.path.join(H, sub), exist_ok=True)
    moved = 0
    for names, sub in ((TOOLS, 'tools'), (DOCS, 'docs'), (STATE, 'state')):
        for n in names:
            src = os.path.join(ROOT, n)
            if os.path.exists(src):
                shutil.move(src, os.path.join(H, sub, n)); moved += 1
    for n in SBX:
        src = os.path.join(ROOT, n)
        if os.path.isdir(src):
            shutil.move(src, os.path.join(H, 'sandbox', n)); moved += 1
    open(os.path.join(H, 'tools', '_paths.py'), 'w', encoding='utf-8').write(PATHS_MOD)
    print(f'  已移动 {moved} 项 → harness/')
    print(f'  已写 _paths.py')
    k = rewrite(TOOLS)
    print(f'  已改路径常量的工具: {k}/{len(TOOLS)}')
    fx = fixups()
    print(f'  已做逐工具语义修正: {fx} 个（钉住项在 ROOT / 兄弟工具在 TOOLS_DIR 的判别）')
    json.dump(dict(backup=d, moved=moved), open(os.path.join(H, 'state', '_reorg.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)

    # ⭐ 改完立刻验；失败自动回滚（拿本会话"改一处漏一处"的教训换来的）
    if not verify():
        print('\n  ⚠️ 验证失败 ⇒ 自动回滚')
        rollback()
        return 1
    print(f'\n  ✅ 重组成功（可回滚: python reorg.py --rollback；备份在 {os.path.basename(d)}）')
    return 0

def rollback():
    cands = sorted([d for d in os.listdir(ROOT) if d.startswith('_reorg_backup_')], reverse=True)
    if not cands: print('  无备份'); return 1
    d = os.path.join(ROOT, cands[0])
    man = json.load(open(os.path.join(d, '_manifest.json'), encoding='utf-8'))
    n = 0
    for name, where in man['manifest'].items():
        src = os.path.join(d, name.rstrip('/'))
        if name.endswith('/'):
            shutil.copytree(src, os.path.join(ROOT, name.rstrip('/')), dirs_exist_ok=True)
        else:
            shutil.copy2(src, os.path.join(ROOT, name.rstrip('/')))
            for sub in ('tools', 'docs', 'state', 'sandbox'):
                q = os.path.join(H, sub, name.rstrip('/'))
                if os.path.exists(q): os.remove(q)
        n += 1
    print(f'  已从 {cands[0]} 还原 {n} 项')
    return 0

if __name__ == '__main__':
    if '--apply' in sys.argv: sys.exit(apply())
    if '--rollback' in sys.argv: sys.exit(rollback())
    sys.exit(plan())
