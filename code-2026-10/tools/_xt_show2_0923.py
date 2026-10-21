import json
raw=json.load(open("D:/hermes/analysis/_xt0923/raw_0923.json",encoding="utf-8"))
for q in ("dl_new","nn_new","transformer","agent_algo","algo_topic","new_llm","code_assist","hermes_topic"):
    items=raw["search"].get(q,[])
    print(f"--- {q} (n={len(items)}) ---")
    for it in items[:8]:
        print(f"{it['full_name']}|{it['stars']}|{it['language']}|{it['created_at']}|{(it['description'] or '')[:95]}")
