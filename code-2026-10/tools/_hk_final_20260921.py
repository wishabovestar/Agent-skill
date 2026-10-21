# -*- coding: utf-8 -*-
import json, io, sys, os, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
t = open(r"D:/hermes/hermes-data/profiles/mybot/memories/MEMORY.md", encoding="utf-8").read()
n = len(t.rstrip("\n"))
print(f"MEMORY {n}/2200 = {100.0*n/2200:.1f}%  (审计前 2171/98.7%)  blocks={t.count('§')+1}")
print("拼接污染:", "YES" if "dump+Hermes" in t else "NO")
snap = json.load(open(r"D:/hermes/hermes-data/profiles/mybot/.skills_prompt_snapshot.json", encoding="utf-8"))
names = [e.get("frontmatter_name") or e.get("skill_name") for e in snap["skills"]]
c = collections.Counter(names)
dup = {k: v for k, v in c.items() if v > 1}
print(f"快照条目={len(names)}  重名对={dup}  (旧的 .bak 重名 arxiv/competitor-news-monitor/grounded-citations 已消除源目录, 待下次快照重生成生效)")
