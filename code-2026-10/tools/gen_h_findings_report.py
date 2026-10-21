#!/usr/bin/env python3
"""生成H级发现人工复核清单 — 从全量扫描提取H级, 按skill分组输出CSV/MD
用法: python gen_h_findings_report.py
"""
import sys, json, csv
sys.path.insert(0, r'D:/hermes/analysis')
from pathlib import Path
from skill_security_scanner import scan_skill
from collections import defaultdict

OUT = Path(r'D:/hermes/data/results')
OUT.mkdir(exist_ok=True)

skills_root = Path(r'D:/hermes/hermes-data/profiles/mybot/skills')
dirs = [d for d in skills_root.rglob('*') if d.is_dir() and (d/'SKILL.md').exists()]

h_findings = []
all_skills = []
for d in dirs:
    r = scan_skill(d)
    all_skills.append(r)
    for f in r['findings']:
        if f['severity'] == 'H':
            f['skill'] = r['skill']
            h_findings.append(f)

# 排序: 按skill聚合
by_skill = defaultdict(list)
for f in h_findings:
    by_skill[f['skill']].append(f)

print(f"=== H级发现复核清单 ===")
print(f"共 {len(h_findings)} 条H级发现, 分布在 {len(by_skill)} 个skills\n")

# CSV导出
csv_path = OUT / 'h_findings_review.csv'
with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['skill', 'pattern', 'severity', 'line', 'evidence', 'decision'])
    for skill, findings in sorted(by_skill.items(), key=lambda x: -len(x[1])):
        for fd in findings:
            w.writerow([fd['skill'], fd['pattern'], fd['severity'], fd['line'],
                        fd['evidence'][:200], ''])  # decision列留空待人工填

# MD导出
md_path = OUT / 'h_findings_review.md'
with open(md_path, 'w', encoding='utf-8') as f:
    f.write('# H级发现人工复核清单 (2026-08-05)\n\n')
    f.write(f'共 {len(h_findings)} 条, {len(by_skill)} 个skills\n\n')
    f.write('| # | skill | pattern | 行 | 证据 | 判定 |\n')
    f.write('|:-:|:------|:--------|:--:|:-----|:----:|\n')
    i = 0
    for skill, findings in sorted(by_skill.items(), key=lambda x: -len(x[1])):
        for fd in findings:
            i += 1
            ev = fd['evidence'].replace('|', '\\|')[:100]
            f.write(f'| {i} | {fd["skill"]} | {fd["pattern"]} | {fd["line"]} | `{ev}` | ⬜ |\n')

print(f"CSV: {csv_path}")
print(f"MD:  {md_path}")
print(f"\nTop 10 H级skills:")
for skill, findings in sorted(by_skill.items(), key=lambda x: -len(x[1]))[:10]:
    print(f"  {skill}: {len(findings)}条")
