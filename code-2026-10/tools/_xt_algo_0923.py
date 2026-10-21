import json
d=json.load(open("D:/hermes/data/agent_knowledge/算法/github_algo_scout_2026-09-23.json",encoding="utf-8"))
print("ALGO_N=",d["count"])
print("QUERIES=",json.dumps(d["queries"],ensure_ascii=False)[:220])
for it in d["items"][:14]:
    print(f"{it['full_name']}|{it['stars']}|{it['language']}|{it['created_at']}|{(it['description'] or '')[:68]}")
