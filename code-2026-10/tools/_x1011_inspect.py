# -*- coding: utf-8 -*-
import json
r = json.load(open("D:/hermes/data/agent_knowledge/算法/xuntian_github_scout_2026-10-11.json", encoding="utf-8"))
na = r["new_all"]
print("=== NEW_ALL by STARS (top 25) ===")
for x in sorted(na, key=lambda z: -(z["stars"] or 0))[:25]:
    print("%d|rel%d|%s|%s|%s|%s" % (x["stars"], x["relevance"], x["full_name"],
          (x.get("created_at") or "")[:10], x.get("language") or "-", (x.get("description") or "")[:75]))
print()
print("=== NEW_ALL by SCORE (top 25) ===")
for x in sorted(na, key=lambda z: -z["score"])[:25]:
    print("%.1f|rel%d|%d|%s|%s" % (x["score"], x["relevance"], x["stars"], x["full_name"],
          (x.get("description") or "")[:70]))
print()
print("=== TRENDING new? ===")
for t in r["trending"][:20]:
    print("%d|+%d|%s|%s|%s" % (t["stars"], t["period_gain"], t["repo"], t["period"], (t["desc"] or "")[:65]))
