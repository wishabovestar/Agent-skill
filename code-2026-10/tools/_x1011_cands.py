# -*- coding: utf-8 -*-
import json, re

KW = {"agent harness":5,"harness":2,"agent skills":3,"agent skill":3,"claude code":3,"claude":2,"mcp":3,
      "multi-agent":3,"multi agent":3,"orchestrat":4,"agent memory":3,"memory":3,"self-improv":3,
      "agentic":2,"skil":2,"code review":2,"compress":2,"tool use":2,"tool router":4,"tool-calling":3,
      "rag":1,"continual learning":2,"coding agent":3,"coding-agent":3,"local-first":1,"deep learning":1,
      "neural":1,"reinforcement learning":1,"inference":2,"vector search":1,"llm":2,"agent":3,
      "context engineering":3,"token":2,"computer use":3,"terminal":1,"cli":1,"gpt":1,"copilot":2,
      "openai":1,"automation":1,"workflow":1,"prompt":2,"gateway":2,"assistant":2,"persistent":1,
      "session":1,"reverse engine":2,"diagram":1,"video":1,"ppt":1,"browser":1,"framework":1,
      "sandbox":1,"security":1,"instinct":2,"memory":3}

def rel(nm, desc):
    t = (nm + " " + (desc or "")).lower()
    s = 0
    for k, v in KW.items():
        if k in t:
            s += v
    return min(10, s)

T = json.load(open("D:/hermes/data/agent_knowledge/算法/tmp/trending_parsed_1011.json", encoding="utf-8"))
R = json.load(open("D:/hermes/data/agent_knowledge/算法/xuntian_github_scout_2026-10-11.json", encoding="utf-8"))
new_all = R["new_all"]

seen = set()
import glob, os
for root in ["D:/hermes/data/agent_knowledge", "D:/hermes/data/math_knowledge",
             "D:/hermes/data/book_knowledge", "D:/hermes/data/physics_knowledge", "D:/hermes/data/intel"]:
    for f in glob.glob(root + "/**/*.json", recursive=True):
        fp = f.replace("\\", "/")
        if "/tmp/" in fp or os.path.basename(fp).startswith("_") or "2026-10-11" in fp:
            continue
        try: d = json.load(open(f, encoding="utf-8", errors="ignore"))
        except Exception: continue
        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in ("full_name","repo","name") and isinstance(v,str) and "/" in v:
                        seen.add(v.split("github.com/")[-1].strip("/").lower())
                    walk(v)
            elif isinstance(o, list):
                for v in o: walk(v)
        walk(d)

cands = []
for t in T:
    r = rel(t["repo"], t.get("desc"))
    if r < 4:
        continue
    cands.append({"full_name": t["repo"], "stars": t.get("stars") or 0, "lang": t.get("lang") or "-",
                  "desc": t.get("desc") or "", "rel": r, "gain": t.get("period_gain") or 0,
                  "period": t.get("period") or "", "is_new": t["repo"].lower() not in seen, "kind": "trend"})
for x in new_all:
    if x["relevance"] < 5:
        continue
    cands.append({"full_name": x["full_name"], "stars": x["stars"], "lang": x.get("language") or "-",
                  "desc": x.get("description") or "", "rel": x["relevance"], "gain": 0,
                  "period": "", "is_new": True, "kind": "new", "created": (x.get("created_at") or "")[:10]})

# dedupe by full_name preferring trend
by = {}
for c in cands:
    if c["full_name"] not in by:
        by[c["full_name"]] = c
cands = list(by.values())

def value(c):
    return c["rel"] * (1 + min(c["stars"], 120000) / 120000.0 + min(c["gain"], 30000) / 30000.0)
cands.sort(key=lambda c: (-value(c), -c["stars"]))
print("=== COMBINED VALUE candidates (rel>=4) ===")
for c in cands[:30]:
    print("%.1f|rel%d|*%d|+%d|%s|%s|new=%s|%s" % (value(c), c["rel"], c["stars"], c["gain"],
          c["full_name"], c["kind"], c["is_new"], c["desc"][:58]))
json.dump(cands, open("D:/hermes/analysis/x1011_cands.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
