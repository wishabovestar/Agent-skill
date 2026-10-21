#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
skill_baseline.py —— 技能质量基线与退化监测

【为什么存在:净增量 P0】
  本机 179 个 SKILL.md,★ 仅有 3 个带质量基线(98.3% 缺失)。
  两档外部研究独立指向同一缺口:
    ★ super-hermes(r1234):`quality_baseline` / `optimal_model` /
      `quality_check_frequency` / ★ `degradation_alert_threshold: 0.10`
    ★ GBrain(r1264):`conformance_version`(技能格式的版本化符合规范)
  ⇒ 本脚本补这一层。

【关键设计:不假装能"打分"】
  ★ 人工给 179 个技能打质量分【不可行】,且"谁打分、怎么打"本身可疑
    (r1234 已暴露:super-hermes 的 quality_baseline:9.8 未说明打分者)。
  ★★ 因此本脚本【不算"质量分"】,只算【机械可复核的结构指标】,
     并以【自身历史】为基线做退化检测 —— 不引入外部主观标尺。

【代理指标(全部可机械复算)】
  bytes           SKILL.md 字节数
  lines           行数
  code_blocks     围栏代码块数(具体性)
  cmds            反引号内命令/标识数(可操作性)
  tables          表格行数(结构化)
  refs            references/ 下文件数(知识深度)
  scripts         scripts/ 下文件数(可运行件)
  sections        ## 级标题数(组织度)
  has_allowed     frontmatter 是否声明 allowed_tools(权限显式)
  has_version     是否声明 version

【退化判据(参照 super-hermes 的 0.10)】
  综合结构分 S = 加权和;若本次 S 相对基线下滑超过阈值 ⇒ 告警。

用法:
  python skill_baseline.py --snapshot            # 首次:建立基线
  python skill_baseline.py --check               # 之后:对比并告警
  python skill_baseline.py --check --threshold 0.10 --json
退出码: 0=无退化 · 1=有退化告警 · 2=用法错
"""
import argparse
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DEFAULT_BASELINE = os.path.join('data', 'skill_baseline.json')
FM_RE = re.compile(r'^---\s*\n(.*?)\n---', re.S)
CODE_RE = re.compile(r'^```', re.M)
CMD_RE = re.compile(r'`([^`\n]{2,80})`')
H2_RE = re.compile(r'^##\s+\S', re.M)

# ★ 权重(和为 1.0);刻意让"可运行件/知识深度"权重最高 —— 因为它们是
#   本机技能真正被使用的部分,而非 prose 长度。
WEIGHTS = {
    'code_blocks': 0.15,
    'cmds':        0.15,
    'tables':      0.10,
    'refs':        0.25,
    'scripts':     0.20,
    'sections':    0.15,
}


def classify(m):
    """★ P1 修正:按【结构特征】自动分组,消除构念偏差。
    实测依据(r1268→r1269):`*-references` 类技能均值仅 0.0532,而 workflow 类 0.3997,
    差 7.5 倍 —— 因为资料索引类【本就不该有 scripts/ 子目录】,低分是构念不符而非质量差。
    ⇒ 因此不跨组比 S 分,只看【同组内】的退化。

    分组规则(优先序,基于实测的结构特征而非名字):
      reference   : 无 scripts,且 refs 多(≥5)  ⇒ 资料索引型
      procedural  : 有 scripts(≥1)             ⇒ 程序性/可执行
      hybrid      : 两者都有,或 refs 多且 sections 多
      prose       : 其余(纯叙述型)
    """
    refs = m.get('refs', 0) or 0
    scr = m.get('scripts', 0) or 0
    sec = m.get('sections', 0) or 0
    if scr >= 1 and refs >= 5:
        return 'hybrid'
    if scr >= 1:
        return 'procedural'
    if refs >= 5:
        return 'reference'
    if refs >= 1 or sec >= 6:
        return 'light'
    return 'prose'
# 归一化上限(达到即满分,防止单个巨型技能拉爆)
CAPS = {'code_blocks': 30, 'cmds': 40, 'tables': 60, 'refs': 40,
        'scripts': 15, 'sections': 25}


def skill_dirs(root='skills'):
    out = []
    for dp, dn, fn in os.walk(root):
        # 跳过归档/隐藏目录
        parts = dp.replace('\\', '/').split('/')
        if any(p.startswith('.') for p in parts):
            continue
        if 'SKILL.md' in fn:
            out.append(dp)
    return sorted(out)


def measure(sdir):
    p = os.path.join(sdir, 'SKILL.md')
    s = io.open(p, encoding='utf-8', errors='replace').read()
    m = {}
    m['bytes'] = len(s.encode('utf-8'))
    m['lines'] = s.count('\n') + 1
    m['code_blocks'] = len(CODE_RE.findall(s)) // 2  # 围栏成对
    m['cmds'] = len(set(CMD_RE.findall(s)))
    m['tables'] = sum(1 for l in s.split('\n') if l.strip().startswith('|'))
    m['sections'] = len(H2_RE.findall(s))

    d = os.path.dirname(p)
    m['refs'] = 0
    m['scripts'] = 0
    for sub, key in (('references', 'refs'), ('scripts', 'scripts')):
        sd = os.path.join(d, sub)
        if os.path.isdir(sd):
            for _dp, _dn, fns in os.walk(sd):
                m[key] += len(fns)

    fm = FM_RE.match(s.lstrip('\ufeff'))
    fms = fm.group(1) if fm else ''
    m['has_allowed'] = bool(re.search(r'^\s*allowed_tools\s*:', fms, re.M))
    m['has_version'] = bool(re.search(r'^\s*version\s*:', fms, re.M))
    return m


def struct_score(m):
    """★ 结构分 S ∈ [0,1]:只反映"结构化程度",★ 不代表内容对不对。"""
    tot = 0.0
    for k, w in WEIGHTS.items():
        cap = CAPS[k]
        tot += w * min(1.0, (m.get(k, 0) or 0) / cap)
    # 两个布尔项各给很小的加分(不主导)
    tot += 0.02 * (1 if m.get('has_allowed') else 0)
    tot += 0.02 * (1 if m.get('has_version') else 0)
    return round(min(1.0, tot), 4)


def build(root='skills'):
    data = {}
    for d in skill_dirs(root):
        try:
            m = measure(d)
        except Exception as e:
            data[d.replace('\\', '/')] = {'error': str(e)}
            continue
        m['S'] = struct_score(m)
        m['group'] = classify(m)   # ★ P1:同组内比较,消除构念偏差
        data[d.replace('\\', '/')] = m
    return data


def summarize(data):
    """★ P1:同时给【全局】与【分组】统计 —— 因为 S 分只在组内可比。"""
    vals = [v['S'] for v in data.values() if 'S' in v]
    if not vals:
        return {}
    vals_sorted = sorted(vals)
    n = len(vals_sorted)
    by_group = {}
    import collections as _c
    g = _c.defaultdict(list)
    for v in data.values():
        if 'S' in v:
            g[v.get('group', 'unknown')].append(v['S'])
    for k, ss in g.items():
        ss2 = sorted(ss)
        by_group[k] = {
            'n': len(ss2),
            'mean_S': round(sum(ss2) / len(ss2), 4),
            'min_S': round(ss2[0], 4),
            'max_S': round(ss2[-1], 4),
        }
    return {
        'count': n,
        'mean_S': round(sum(vals) / n, 4),
        'median_S': round(vals_sorted[n // 2], 4),
        'min_S': round(vals_sorted[0], 4),
        'max_S': round(vals_sorted[-1], 4),
        'by_group': by_group,
    }


def main():
    ap = argparse.ArgumentParser(description='技能质量基线与退化监测')
    ap.add_argument('--snapshot', action='store_true', help='建立/覆盖基线')
    ap.add_argument('--check', action='store_true', help='对比基线并告警')
    ap.add_argument('--baseline', default=DEFAULT_BASELINE)
    ap.add_argument('--threshold', type=float, default=0.10,
                    help='退化告警阈值(默认 0.10, 参照 super-hermes)')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    if not (a.snapshot or a.check):
        sys.stderr.write('用法错: 需指定 --snapshot 或 --check\n')
        return 2

    cur = build('skills')
    summ = summarize(cur)

    if a.snapshot:
        d = os.path.dirname(a.baseline)
        if d:
            os.makedirs(d, exist_ok=True)
        io.open(a.baseline, 'w', encoding='utf-8').write(
            json.dumps({'summary': summ, 'skills': cur}, ensure_ascii=False, indent=1))
        print('★ 基线已建立 → %s' % a.baseline)
        print('  技能数 %d · 均值 S=%.4f · 中位 %.4f · 范围 [%.4f, %.4f]'
              % (summ['count'], summ['mean_S'], summ['median_S'],
                 summ['min_S'], summ['max_S']))
        print('  ── ★ 分组(★ S 分只在【组内】可比)──')
        for k, v in sorted(summ.get('by_group', {}).items(),
                           key=lambda x: -x[1]['n']):
            print('    %-12s n=%-4d 均值=%.4f  范围[%.4f, %.4f]'
                  % (k, v['n'], v['mean_S'], v['min_S'], v['max_S']))
        return 0

    # check
    if not os.path.isfile(a.baseline):
        sys.stderr.write('用法错: 基线不存在 %s ⇒ 先跑 --snapshot\n' % a.baseline)
        return 2
    base = json.load(io.open(a.baseline, encoding='utf-8'))
    bsk = base.get('skills', {})

    regressed, improved, gone = [], [], []
    for path, m in cur.items():
        if 'S' not in m:
            continue
        b = bsk.get(path)
        if not b or 'S' not in b:
            continue
        delta = m['S'] - b['S']
        if delta < 0 and abs(delta) >= a.threshold * max(b['S'], 1e-6):
            regressed.append({'path': path, 'before': b['S'], 'after': m['S'],
                              'delta': round(delta, 4)})
        elif delta > 0 and abs(delta) >= a.threshold * max(b['S'], 1e-6):
            improved.append({'path': path, 'before': b['S'], 'after': m['S'],
                             'delta': round(delta, 4)})
    for path in bsk:
        if path not in cur:
            gone.append(path)

    bs = base.get('summary', {}).get('mean_S')
    cs = summ.get('mean_S')
    mean_delta = (cs - bs) if (bs is not None and cs is not None) else None
    overall = None
    if mean_delta is not None and bs:
        overall = mean_delta / bs
    alert = bool(regressed) or bool(gone) or (
        overall is not None and overall < -a.threshold)

    out = {
        'baseline': os.path.abspath(a.baseline),
        'threshold': a.threshold,
        'summary_now': summ,
        'summary_baseline': base.get('summary', {}),
        'mean_delta': (round(mean_delta, 4) if mean_delta is not None else None),
        'mean_delta_pct': (round(overall * 100, 2) if overall is not None else None),
        'regressed': regressed, 'improved': improved, 'removed': gone,
        'alert': alert,
    }
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print('=' * 64)
        print('技能质量基线 · 退化检查')
        print('=' * 64)
        print('  基线: %s' % os.path.basename(a.baseline))
        print('  均值 S: 基线 %.4f → 现在 %.4f (%s%%)'
              % (bs if bs is not None else -1, cs if cs is not None else -1,
                 out['mean_delta_pct']))
        print('  阈值 %.0f%% · 退化技能 %d 个 · 改进 %d 个 · 消失 %d 个'
              % (a.threshold * 100, len(regressed), len(improved), len(gone)))
        print('-' * 64)
        if regressed:
            print('  ★ 退化告警:')
            for r in regressed[:15]:
                print('    LOSS %-52s %.4f → %.4f' % (r['path'][:52], r['before'], r['after']))
        if gone:
            print('  ★ 消失:')
            for g in gone[:10]:
                print('    GONE %s' % g[:70])
        if improved:
            print('  ✓ 改进(前 8):')
            for r in improved[:8]:
                print('    GAIN %-52s %.4f → %.4f' % (r['path'][:52], r['before'], r['after']))
        print('-' * 64)
        print('  ★ 判定: %s' % ('ALERT 有退化' if alert else 'OK 无退化'))
        print('  ★ 说明: S 只是【结构分】,不反映内容正确性 —— 它只回答')
        print('         「技能有没有变得更空/更少可执行件」,不回答「写得对不对」。')
        print('=' * 64)

    return 1 if alert else 0


if __name__ == '__main__':
    sys.exit(main())
