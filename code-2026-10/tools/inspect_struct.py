import json, glob, os

# inspect structures of a few representative files
samples = [
    "D:/hermes/data/agent_knowledge/算法/github_algo_scout_2026-10-02.json",
    "D:/hermes/data/agent_knowledge/algorithm/机器学习/2026-10-02.json",
    "D:/hermes/data/agent_knowledge/算法/xuntian_github_scout_2026-09-25.json",
]
for s in samples:
    if not os.path.exists(s):
        print("MISS", s); continue
    try:
        d = json.load(open(s, encoding="utf-8"))
    except Exception as e:
        print("ERR", s, e); continue
    if isinstance(d, dict):
        print(os.path.basename(s), "keys=", list(d.keys())[:12])
        for k in d:
            if isinstance(d[k], list) and d[k] and isinstance(d[k][0], dict):
                print("   list", k, "len", len(d[k]), "itemkeys", list(d[k][0].keys())[:10])
    elif isinstance(d, list):
        print(os.path.basename(s), "LIST len", len(d), "itemkeys", list(d[0].keys())[:10] if d and isinstance(d[0], dict) else "?")
