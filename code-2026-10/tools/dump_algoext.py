import json
d = json.load(open("D:/hermes/data/agent_knowledge/算法/algo_ext_2026-10-02.json", encoding="utf-8"))
print("algo_ext count", d["count"])
for x in d["repos"][:14]:
    print(f"★{x['stars']:>6} {x['full_name'][:40]:40} | {x['desc'][:60]}")
