# -*- coding: utf-8 -*-
"""汇总：巡天 + 新闻 → 两份可读摘要"""
import sys, io, json, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

xt = json.load(open(sorted(glob.glob("D:/hermes/analysis/_xt_update_*.json"))[-1], encoding="utf-8"))
nw = json.load(open(sorted(glob.glob("D:/hermes/analysis/_news_update2_*.json"))[-1], encoding="utf-8"))

L = []
L.append(f"# 巡天采集 {xt['run_at']}  seen={xt['seen_repos']}")
L.append("## 查询")
for q in xt["queries"]:
    L.append(f"- [{q['tag']}] {q['q'][:60]} total={q['total']} kept={q['kept']}")
L.append(f"\n## 新增仓库 ({len(xt['repos_new'])})")
for r in xt["repos_new"]:
    L.append(f"- {r['full_name']} ★{r['stars']} created={r['created']} pushed={r['pushed']} lang={r['lang']}\n  {r['desc']}")
L.append(f"\n## 已归档(重复) {len(xt['repos_dup'])} 条，按星取前 12")
for r in sorted(xt["repos_dup"], key=lambda x: -(x["stars"] or 0))[:12]:
    L.append(f"- {r['full_name']} ★{r['stars']} created={r['created']}")
L.append(f"\n## arXiv ({len(xt['papers'])}) 按主题")
by = {}
for p in xt["papers"]:
    by.setdefault(p["topic"], []).append(p)
for t, ps in by.items():
    L.append(f"### {t}")
    for p in ps:
        L.append(f"- {p['id']} | {p['date']} | {p['title'][:110]}")
open("D:/hermes/analysis/_xt_report_1020.md", "w", encoding="utf-8").write("\n".join(L))
print("XT lines", len(L))

N = []
N.append(f"# 新闻 {nw['run_at']}")
N.append("## 新浪滚动")
for i, s in enumerate(nw["sina"], 1):
    N.append(f"{i}. {s['title']}  [{s['time']}]")
N.append("\n## IT之家")
for i, s in enumerate(nw["ithome"][:40], 1):
    N.append(f"{i}. {s['title']}  [{s['pub']}]")
N.append("\n## arXiv cs.AI 最新")
for i, s in enumerate(nw["arxiv"], 1):
    N.append(f"{i}. {s['title'][:100]}  [{s['date']}] {s['url']}")
N.append("\n## WHO DON")
for i, s in enumerate(nw["who"], 1):
    N.append(f"{i}. {s['date']} {s['title']}")
N.append("\n## HN front page")
for i, s in enumerate(nw["hn"], 1):
    N.append(f"{i}. {s['title']}  ({s['points']} pts)")
N.append(f"\n## 碳酸锂 LC0\n{nw['price']['raw'] if nw['price'] else 'N/A'}")
open("D:/hermes/analysis/_news_report_1020.md", "w", encoding="utf-8").write("\n".join(N))
print("NEWS lines", len(N))
