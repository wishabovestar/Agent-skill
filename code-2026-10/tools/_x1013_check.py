# -*- coding: utf-8 -*-
import json, os
d = "D:/hermes/data/agent_knowledge/算法"
for f in ["xuntian_github_scout_2026-10-13.json", "xuntian_github_scout_2026-10-13.md",
          "algo_ext_2026-10-13.json", "github_algo_scout_2026-10-13.json"]:
    p = os.path.join(d, f)
    print("FILE", f, os.path.exists(p), os.path.getsize(p) if os.path.exists(p) else "-")

a = json.load(open(os.path.join(d, "algo_ext_2026-10-13.json"), encoding="utf-8"))
print("algo_ext count", a["count"], "repos", len(a["repos"]))
g = json.load(open(os.path.join(d, "github_algo_scout_2026-10-13.json"), encoding="utf-8"))
print("github_algo_scout count", g["count"], "items", len(g["items"]))
R = json.load(open(os.path.join(d, "xuntian_github_scout_2026-10-13.json"), encoding="utf-8"))
print("report: seen=%d pool=%d unique=%d new=%d agent=%d algo=%d trending=%d top10=%d"
      % (R["seen_repos"], R["pool"], R["unique_repos"], R["new_count"], R["agent_new_count"],
         R["algo_new_count"], R["trending_count"], len(R["top10"])))
lg = json.load(open(os.path.join(d, "_collection_log.json"), encoding="utf-8"))
print("log last:", json.dumps(lg[-1], ensure_ascii=False))
print("--- algo repos ---")
for r in sorted(a["repos"], key=lambda z: -(z["stars"] or 0)):
    print("  %s|*%d|%s|%s" % (r["full_name"], r["stars"], r.get("language") or "-", (r.get("created_at") or "")[:10]))
