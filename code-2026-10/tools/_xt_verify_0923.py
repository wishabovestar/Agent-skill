import json
d=json.load(open("D:/hermes/data/agent_knowledge/ai_agent/github_scout_2026-09-23.json",encoding="utf-8"))
print("=== NEW ITEMS (is_new) ===")
for it in sorted([x for x in d["top"] if x.get("is_new")],key=lambda x:-x["relevance"])[:14]:
    print(f"{it['full_name']}|{it['stars']}|{it['relevance']}|{it['language']}|{it['created_at']}|{it['license']}|{(it['description'] or '')[:80]}")
print("=== TOP10 (report order) ===")
for i,it in enumerate(sorted([x for x in d["top"] if x["relevance"]>=6],key=lambda x:(-x["relevance"],not x["is_new"],-x["stars"]))[:10],1):
    print(f"{i}. {it['full_name']} {it['stars']} rel={it['relevance']} new={it['is_new']}")
