# -*- coding: utf-8 -*-
import json
R = json.load(open("D:/hermes/data/agent_knowledge/算法/xuntian_github_scout_2026-10-13.json", encoding="utf-8"))
print("== NEW ALL (%d) ==" % len(R["new_all"]))
for x in R["new_all"]:
    print("%-42s *%-6d rel%-2d %-12s %s | %s" % (x["full_name"], x["stars"], x["relevance"],
          (x.get("language") or "-")[:12], (x.get("created_at") or "")[:10], (x.get("description") or "")[:62]))
print("== TRENDING (top by gain) ==")
for t in sorted(R["trending"], key=lambda z: -(z.get("period_gain") or 0))[:20]:
    print("%-40s *%-7d +%-7d %-6s | %s" % (t["repo"], t["stars"], t.get("period_gain") or 0,
          t.get("period") or "", (t.get("desc") or "")[:58]))
