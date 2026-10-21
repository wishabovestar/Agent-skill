import json
raw=json.load(open("D:/hermes/analysis/_xt0923/raw_0923.json",encoding="utf-8"))
for q in ("hermes_topic","new_agents","ai_agent","mcp_server","search_engine","cli_tool"):
    items=raw["search"].get(q,[])
    print(f"--- {q} (n={len(items)}) ---")
    for it in items[:15]:
        print(f"{it['full_name']}|{it['stars']}|{it['language']}|{it['created_at']}|{(it['description'] or '')[:85]}")
