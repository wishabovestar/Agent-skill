import json
for p in ["D:/hermes/data/agent_knowledge/算法/xuntian_github_scout_2026-10-02.json",
          "D:/hermes/data/agent_knowledge/算法/algo_ext_2026-10-02.json"]:
    d = json.load(open(p, encoding="utf-8"))
    print(p.split("/")[-1], "OK keys:", list(d.keys())[:8])
d = json.load(open("D:/hermes/data/agent_knowledge/算法/xuntian_github_scout_2026-10-02.json", encoding="utf-8"))
print("top10 count", len(d["top10"]), "new_all", len(d["new_all"]), "trending", len(d["trending"]))
for x in d["top10"]:
    print(f"  {x['full_name']} | ★{x['stars']} | {x.get('created','')[:10]} | {x['url']}")
