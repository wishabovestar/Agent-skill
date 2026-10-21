import json, re

seen = set(json.load(open("D:/hermes/analysis/seen_repos.json", encoding="utf-8")))
trending = json.load(open("D:/hermes/analysis/trending_parsed.json", encoding="utf-8"))
main = json.load(open("D:/hermes/analysis/gh_main.json", encoding="utf-8"))
algo = json.load(open("D:/hermes/analysis/gh_algo.json", encoding="utf-8"))
supp = json.load(open("D:/hermes/analysis/gh_supp.json", encoding="utf-8"))

KW = {"hermes": 6, "agent": 5, "mcp": 5, "llm": 4, "skill": 4, "claude": 4,
      "ai agent": 6, "code assistant": 5, "copilot": 4, "autonomous": 3,
      "tool use": 4, "tool-use": 4, "function calling": 3, "rag": 3, "context": 2,
      "workflow": 2, "orchestrat": 3, "cli": 2, "search": 2, "openai": 3,
      "gpt": 3, "gemini": 2, "deepseek": 3, "deep learning": 4, "neural": 4,
      "transformer": 3, "attention": 3, "quantiz": 3, "fine-tun": 3,
      "mixture-of-experts": 3, "moe": 2, "inference": 3, "embedding": 2,
      "vector": 2, "reinforcement": 3, "agentic": 5, "harness": 3, "multimodal": 2}

def score(name, desc, topics, stars):
    text = (name + " " + (desc or "") + " " + " ".join(topics or [])).lower()
    raw = 0; hits = []
    for kw, w in KW.items():
        if kw in text:
            raw += w; hits.append(kw)
    st = stars or 0
    coef = 1.0 if st >= 3000 else 0.9 if st >= 1000 else 0.78 if st >= 300 else 0.65 if st >= 100 else 0.5
    return round(raw * coef, 2), hits

def mk(fn, stars, desc, lang, created, topics, url, forks=None, src=""):
    s, hits = score(fn, desc or "", topics or [], stars)
    return {"full_name": fn, "stars": stars, "forks": forks, "lang": lang,
            "desc": (desc or "")[:220], "created": created, "topics": topics or [],
            "url": url or ("https://github.com/" + fn), "score": s, "hits": hits, "src": src}

pool = {}
for t in trending:
    fn = t["repo"]; key = fn.lower()
    if key in pool: continue
    pool[key] = mk(fn, t.get("stars"), t.get("desc"), "", "", [],
                   "https://github.com/" + fn, forks=t.get("forks"), src="trend:" + t.get("period", ""))

for data in (main, algo, supp):
    for q, blob in data.items():
        for i in (blob.get("items") or []):
            fn = i.get("full_name")
            if not fn: continue
            key = fn.lower()
            if key in pool:
                if q[:20] not in pool[key]["src"]:
                    pool[key]["src"] += "|" + q[:20]
                continue
            pool[key] = mk(fn, i.get("stars"), i.get("description"), i.get("language"),
                           i.get("created_at"), i.get("topics"), i.get("url"),
                           forks=i.get("forks"), src=q[:26])

new = [v for k, v in pool.items() if k not in seen]
new.sort(key=lambda x: (-x["score"], -(x["stars"] or 0)))

AGENT_RE = re.compile(r"agent|hermes|mcp|skill|claude|llm|copilot|tool|code assist|orchestrat|rag|inference|prompt", re.I)
agent_new = [x for x in new if AGENT_RE.search(x["full_name"] + " " + x["desc"] + " " + " ".join(x["topics"]))]

print(f"POOL={len(pool)} NEW={len(new)} AGENT_NEW={len(agent_new)} SEEN={len(seen)}")
json.dump(new, open("D:/hermes/analysis/new_all.json", "w", encoding="utf-8"), ensure_ascii=False)
print("\n=== TOP 20 NEW (all) ===")
for x in new[:20]:
    print(f"{x['score']:>5} ★{x['stars']:>6} {x['full_name'][:46]:46} [{str(x['lang'])[:10]:10}] {x['desc'][:60]}")
print("\n=== TOP 15 NEW agent/toolchain ===")
for x in agent_new[:15]:
    print(f"{x['score']:>5} ★{x['stars']:>6} {x['full_name'][:46]:46} [{str(x['lang'])[:10]:10}] {x['desc'][:60]}")
