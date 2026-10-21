import json
d = json.load(open("D:/hermes/data/agent_knowledge/算法/xuntian_github_scout_2026-10-02.json", encoding="utf-8"))
for k in ("queries_total","seen_repos","pool","new_count","agent_new_count","algo_new_count","trending_count"):
    print(k, "=", d[k])
print("queries:", len(d["queries"]))
