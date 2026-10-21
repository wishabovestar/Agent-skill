import json, re
new = json.load(open("D:/hermes/analysis/new_all.json", encoding="utf-8"))
AG = re.compile(r"agent|hermes|mcp|skill|claude|llm|copilot|tool|code assist|orchestrat|rag|inference|prompt|memory|gateway|harness", re.I)
ag = [x for x in new if AG.search(x["full_name"] + " " + x["desc"] + " " + " ".join(x["topics"] or []))]
ag.sort(key=lambda x: -x["score"])
print("AGENT_NEW=", len(ag))
for n, x in enumerate(ag, 1):
    print(f"{n:>2}|{x['score']:>5}|★{x['stars']:>6}|{x['full_name'][:42]:42}|{(x['created'] or '')[:10]}|{x['desc'][:58]}")
