#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
check_recent_archives.py —— 对最近 N 档归档批量跑纪律检查(P1 ⑦ 落地)

【为什么】
  r1266 造了 `discipline_check.py`,但它【只被手工调用过】⇒ 未接入写作流程。
  本脚本把它接到"每批归档落盘后"这一步。

【关键设计:★ 不假装能自动分类】
  r1266 已实测:检查器【判不了"报告属于哪类"】(机械方法只能判机械构造那一半)。
  ⇒ 因此本脚本【不猜类型】,而是:
    ★ 对每档跑【全部适用 profile】,把结果【如实列出】,由人看。
    ★ 并明确输出"该 profile 是否适用"的提示,而不是给一个总分。

用法:
  python check_recent_archives.py            # 最近 8 档
  python check_recent_archives.py --n 20
  python check_recent_archives.py --n 20 --json
退出码: 0=全部无缺项 · 1=存在缺项(★ 不一定是问题,见下) · 2=用法错
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def recent(n):
    d = os.path.join(ROOT, 'knowledge_base', 'research')
    rows = []
    for f in os.listdir(d):
        m = re.match(r'^r(\d+)_(.+)\.md$', f)
        if m:
            rows.append((int(m.group(1)), f))
    rows.sort(reverse=True)
    return rows[:n]


def run_one(path, profile):
    p = subprocess.run(
        [sys.executable, '-X', 'utf8',
         os.path.join(HERE, 'discipline_check.py'),
         '--profile', profile, '--report', path, '--json'],
        capture_output=True, text=True, encoding='utf-8', errors='replace')
    try:
        return json.loads(p.stdout)
    except Exception:
        return {'error': 'parse_fail', 'raw': (p.stdout or p.stderr)[:200]}


def main():
    ap = argparse.ArgumentParser(description='批量纪律检查')
    ap.add_argument('--n', type=int, default=8, help='检查最近 N 档')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    rows = recent(a.n)
    profiles = ['mechanism', 'study', 'benchmark', 'acceptance']
    out = []
    for rid, fn in rows:
        path = os.path.join(ROOT, 'knowledge_base', 'research', fn)
        rec = {'rid': 'r%d' % rid, 'file': fn, 'profiles': {}}
        for prof in profiles:
            r = run_one(path, prof)
            rec['profiles'][prof] = {
                'score': r.get('score'),
                'verdict': r.get('verdict'),
                'total': r.get('total'),
                'missing': [m['id'] for m in r.get('missing', [])],
            }
        out.append(rec)

    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print('=' * 78)
        print('最近 %d 档 · 纪律检查(★ 检查器【不判类型】,故列出全部 profile 供你判断)' % len(out))
        print('=' * 78)
        print('  %-7s %-11s %-11s %-11s %-11s'
              % ('rid', 'mechanism', 'study', 'benchmark', 'acceptance'))
        print('  ' + '-' * 74)
        for rec in out:
            cells = []
            for prof in profiles:
                p = rec['profiles'][prof]
                if p['total'] in (0, None):
                    cells.append('n/a')
                else:
                    cells.append('%d/%d' % (p['score'] * p['total'] if p['score'] is not None else 0,
                                            p['total']))
            print('  %-7s %-13s %-13s %-13s %-13s'
                  % (rec['rid'], cells[0], cells[1], cells[2], cells[3]))
        print('=' * 78)
        print('  ★ 读法:')
        print('    · mechanism 档 ⇒ 全 n/a 正常(无适用项)')
        print('    · 研究档 ⇒ 看 study 列;跑分档 ⇒ 看 benchmark 列;验收档 ⇒ 看 acceptance 列')
        print('    · ★【低分 ≠ 质量差】—— 先确认 profile 与该档类型匹配(r1266 实测教训)')
        print('=' * 78)

    bad = sum(1 for rec in out for p in rec['profiles'].values() if p.get('missing'))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
