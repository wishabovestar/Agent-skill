#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
discipline_check.py —— 报告纪律检查器

【来源:两档外部研究的可落地纪律】
  ★ r1264 GBrain —— 六条评测诚实纪律(README 一手提炼):
     G1 严格/宽松指标都要定义,并说明为何用严格
     G2 公开指标天花板(如 k=5 上限 99.4%)
     G3 竞品数字要自己重算并标注 recomputation(不引用其宣称)
     G4 明确界定测量范围(如 retrieval only, no reader)
     G5 带版本号
     G6 带日期 + 运行次数

  ★ r1259 RSIAgent DRS —— 四条出题防作弊纪律:
     D1 不得预先解题(no preflight / secretly producing the solution)
     D2 交接物不得携带答案/私有理由(no answer leakage)
     D3 验收须用 fresh 执行者 + 干净环境(fresh actor / clean env)
     D4 不得只测正向(需有反例/失败关闭测试)

【设计原则】
  ★ 本检查器只做【机械可判】的检查(关键词/结构)——
    与 r1240 的结论一致:子串类只能覆盖"机械构造"那一半。
  ★ 因此每项结论都带【证据行号】,由人复核;
    ★ 命中 ≠ 内容正确,只表示【该纪律被显式写到】。

用法:
  python discipline_check.py --report <报告文件> [--json] [--min-score 0.7]
退出码: 0=全部达标 · 1=有缺项 · 2=用法错
"""
import argparse
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')


# ── 检查项定义 ───────────────────────────────────────────────────────
# 每项: (id, 组, 名称, 说明, 命中正则列表, 必需)
# ★ 已知限制(实测获得):
#   ① 正则必须【足够具体】否则假阳性 —— 实测 `预[先解]` 会命中"预先定义",
#      `fresh` 会命中"keeps fresh" ⇒ 全部加长、要求搭配词。
#   ② ★★ 【报告类型必须区分】—— D1-D4 是【基准/验收报告】的纪律,
#      不适用于"外部项目研究档" ⇒ 引入 --profile 只检查适用组。
PROFILES = {
    # ★ 机制/原理拆解档:讲清"它怎么工作",不涉及跑分与验收 ⇒ 不适用 G/D 组
    'mechanism': [],
    # 外部项目/论文研究档:只适用 GBrain 组的"报告诚实"部分
    'study':    ['G1', 'G2', 'G3', 'G4', 'G5', 'G6'],
    # 基准跑分报告:GBrain 全组
    'benchmark': ['G1', 'G2', 'G3', 'G4', 'G5', 'G6'],
    # 实验/验收报告:GBrain 全组 + DRS 全组
    'acceptance': ['G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'D1', 'D2', 'D3', 'D4'],
    # 全查(会给机制档/研究档误报 ⇒ 仅诊断用)
    'all': ['G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'D1', 'D2', 'D3', 'D4'],
}

# ★★ 已知限制(实测定标,务必先读):
#   ★ profile 必须【人工选择正确】,选错会大规模误报 —— 实测:
#     · r1264(外部研究档)用 all     → 误报 2 项(D2/D4 不适用)
#     · r1259(机制拆解档)用 acceptance → 报 8 项缺项(★ 但它是"讲机制",本就不该有跑分/验收纪律)
#   ⇒ ★★ 这与 r1240 的结论同源:【机械方法只能判"机械构造"那一半】,
#      "这份报告属于哪种类型"本身是语义判断 ⇒ 本工具【不做自动分类】,由人指定。
#   ⇒ ★★ 因此:**检查器报低分 ≠ 报告质量差**,必须先确认 profile 选对了。

CHECKS = [
    # ── GBrain 六条 ────────────────────────────────────────────────
    ('G1', 'GBrain', '严格/宽松指标定义',
     '须明确区分严格与宽松口径',
     [r'严格\s*(vs|与|/)\s*宽松', r'strict[^。\n]{0,20}loose', r'any[- ]hit', r'recall_all@'],
     True),
    ('G2', 'GBrain', '指标天花板',
     '须公开该指标的理论上限(如 k=5 上限)',
     [r'天花板', r'理论(最[大高]|上限)', r'ceiling', r'99\.4%'],
     True),
    ('G3', 'GBrain', '竞品数字自算',
     '引用他人数字须自己重算并标注',
     [r'recomputation', r'自行(复算|重算)', r'我们(按|用).{0,12}重算', r'复算.{0,10}得'],
     True),
    ('G4', 'GBrain', '测量范围界定',
     '须说明测的是什么、不含什么',
     [r'retrieval only', r'仅检索', r'不含\s*reader', r'no reader', r'范围界定'],
     True),
    ('G5', 'GBrain', '版本号',
     '须带被测系统的版本',
     [r'\bv\d+\.\d+', r'版本\s*[:：]', r'"version"', r'\d+\.\d+\.\d+\.\d+'],
     True),
    ('G6', 'GBrain', '日期与运行次数',
     '须带测量日期与运行次数',
     [r'Measured\s*20\d\d', r'运行\s*\d+\s*次', r'single run', r'单次运行', r'k\s*=\s*\d+'],
     True),
    # ── DRS 四条(★ 仅适用于基准/验收报告)──────────────────────────
    # ★★ 召回修正(r1276 实测:原正则 D1 仅 2/8=25%,总召回 15/30=50%):
    #    · `preflight.{0,20}solution` 的 20 字符窗口【太窄】—— 英文原文里两词距离远超 20;
    #    · 中文写法多是"出题时不得预先产出答案"这类【无 preflight 词的表述】⇒ 需补语义词。
    #    ⇒ 全部放宽窗口并补同义表达;★ 但仍不可能 100%(见 recall_test_dgroup.py)。
    ('D1', 'DRS', '未预先解题',
     '出题者不得预先解出答案',
     [r'不得先自己解', r'no preflight', r'preflight.{0,120}solution',
      r'不预先(解|产出)', r'pre-?solv', r'不得(提前|预先)[^。\n]{0,12}(做掉|解出|产出)',
      r'不能先(偷着|悄悄)[^。\n]{0,12}答案', r'出题[^。\n]{0,20}不该自己'],
     True),
    ('D2', 'DRS', '无答案泄漏',
     '交接物/样本不得携带答案',
     [r'不得放入答案', r'不得携[带].{0,8}答案', r'答案泄漏', r'样本.{0,8}不携[带]',
      r'answer leak', r'不(许|得|要)[^。\n]{0,10}(夹带|混)[^。\n]{0,6}答案',
      r'must not be placed with answers', r'must not carry the answer',
      r'别把答案[^。\n]{0,10}(混|放)'],
     True),
    ('D3', 'DRS', 'fresh 验收者+干净环境',
     '验收须由全新执行者在干净环境做',
     [r'fresh\s+(actor|执行者|实例)', r'全新(执行者|实例|环境)', r'干净环境',
      r'clean env', r'新建实例', r'没参与过[^。\n]{0,12}(人|者)',
      r'空环境[^。\n]{0,10}再跑'],
     True),
    ('D4', 'DRS', '反例/失败关闭测试',
     '须有反向测试(故意破坏并断言检出)',
     [r'反例测试', r'失败关闭', r'fail[- ]closed', r'伪造.{0,10}(就绪|token|信号)',
      r'故意.{0,8}破坏', r'negative test', r'falsification', r'故意[^。\n]{0,10}(搞坏|弄坏)'],
     True),
]


def scan(report_text, profile='all'):
    """★ 缺陷修正②:按 --profile 只检查【适用的组】,
    否则"外部项目研究档"会被 D 组误报缺项(实测 r1264 即如此)。"""
    enabled = set(PROFILES.get(profile, PROFILES['all']))
    lines = report_text.split('\n')
    results = []
    for cid, grp, name, desc, pats, required in CHECKS:
        if cid not in enabled:
            continue
        hits = []
        for rx in pats:
            r = re.compile(rx, re.I)
            for i, line in enumerate(lines, 1):
                if r.search(line):
                    hits.append((i, line.strip()[:110]))
                    break  # 每个正则只记首行
        results.append({
            'id': cid, 'group': grp, 'name': name, 'desc': desc,
            'required': required, 'passed': len(hits) > 0,
            'evidence': hits[:3],
        })
    return results


def main():
    ap = argparse.ArgumentParser(description='报告纪律检查器 (GBrain 六条 + DRS 四条)')
    ap.add_argument('--report', required=True, help='待检查的报告文件')
    ap.add_argument('--profile', default='study',
                    choices=list(PROFILES.keys()),
                    help='报告类型: study(外部研究档,默认) / benchmark(跑分) / '
                         'acceptance(实验验收,含D组) / all')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--min-score', type=float, default=1.0,
                    help='通过阈值(默认 1.0=全过)')
    a = ap.parse_args()

    if not os.path.isfile(a.report):
        sys.stderr.write('用法错: 文件不存在 %s\n' % a.report)
        return 2

    txt = io.open(a.report, encoding='utf-8', errors='replace').read()
    res = scan(txt, a.profile)
    passed = sum(1 for r in res if r['passed'])
    total = len(res)
    # ★ 缺陷修正④:total=0 时【不得报 100%】——
    #   mechanism 这类"无适用检查项"的 profile 会算出空集 ⇒ 报满分会误导。
    if total == 0:
        score = None
        verdict = 'N/A'
    else:
        score = passed / total
        verdict = 'PASS' if score >= a.min_score else 'INCOMPLETE'
    missing = [r for r in res if not r['passed']]

    out = {
        'report': os.path.abspath(a.report),
        'profile': a.profile,
        'report_chars': len(txt),
        'total': total, 'passed': passed,
        'score': (round(score, 3) if score is not None else None),
        'verdict': verdict,
        'missing': [{'id': r['id'], 'name': r['name'], 'desc': r['desc']} for r in missing],
        'checks': res,
    }

    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print('=' * 66)
        print('报告纪律检查  (GBrain 六条评测诚实 + DRS 四条出题防作弊)')
        print('=' * 66)
        print('  %s (%d 字符) · profile=%s'
              % (os.path.basename(a.report), out['report_chars'], a.profile))
        print('-' * 66)
        cur = None
        for r in res:
            if r['group'] != cur:
                cur = r['group']
                print('  【%s】' % cur)
            mark = '✓' if r['passed'] else '✗'
            ev = ('  ← L%d: %s' % (r['evidence'][0][0], r['evidence'][0][1])) if r['evidence'] else ''
            print('    %s %-3s %-18s%s' % (mark, r['id'], r['name'], ev))
        print('-' * 66)
        if score is None:
            print('  ★ 本 profile 【无适用检查项】(如 mechanism=纯机制拆解档)')
            print('  ★ 判定: N/A —— ★【不是满分】,是"这套纪律不适用于本类型报告"')
            print('  ★ 要检查跑分诚实请用 --profile benchmark / study;')
            print('    要检查验收纪律请用 --profile acceptance。')
        else:
            print('  得分: %d/%d = %.1f%%   ★ 判定: %s (阈值 %.0f%%)'
                  % (passed, total, score * 100, verdict, a.min_score * 100))
            if missing:
                print('  ★ 缺项:')
                for m in missing:
                    print('     - %s %s:%s' % (m['id'], m['name'], m['desc']))
        print('=' * 66)

    if score is None:
        return 0
    return 0 if score >= a.min_score else 1


if __name__ == '__main__':
    sys.exit(main())
