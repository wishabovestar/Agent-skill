import json, re, os

seen = set(json.load(open("D:/hermes/analysis/seen_repos.json", encoding="utf-8")))

trending = json.load(open("D:/hermes/analysis/trending_parsed.json", encoding="utf-8"))
main = json.load(open("D:/hermes/analysis/gh_main.json", encoding="utf-8"))
algo = json.load(open("D:/hermes/analysis/gh_algo.json", encoding="utf-8"))

# ---- keyword scoring ----
KW = {
    "hermes": 6, "agent": 5, "mcp": 5, "llm": 4, "skill": 4, "claude": 4,
    "ai agent": 6, "code assistant": 5, "copilot": 4, "autonomous": 3,
    "tool use": 4, "tool-use": 4, "function calling": 3, "rag": 3, "context": 2,
    "workflow": 2, "orchestrat": 3, "cli": 2, "search": 2, "openai": 3,
    "gpt": 3, "gemini": 2, "deepseek": 3, "deep learning": 4, "neural": 4,
    "transformer": 3, "attention": 3, "quantiz": 3, "fine-tun": 3,
    "mixture-of-experts": 3, "moe": 2, "inference": 3, "embedding": 2,
    "vector": 2, "rl": 2, "reinforcement": 3, "agentic": 5, "harness": 3,
}

def score(name, desc, topics, stars):
    text = (name + " " + (desc or "") + " " + " ".join(topics or [])).lower()
    raw = 0
    hits = []
    for kw, w in KW.items():
        if kw in text:
            raw += w
            hits.append(kw)
    st = stars or 0
    if st >= 3000: coef = 1.0
    elif st >= 1000: coef = 0.9
    elif st >= 300: coef = 0.78
    elif st >= 100: coef = 0.65
    else: coef = 0.5
    return round(raw * coef, 2), hits

def mk(full_name, stars, desc, lang, created, topics, url, forks=None, src=""):
    s, hits = score(full_name, desc or "", topics or [], stars)
    return {"full_name": full_name, "stars": stars, "forks": forks, "lang": lang,
            "desc": (desc or "")[:220], "created": created, "topics": topics or [],
            "url": url or ("https://github.com/" + full_name), "score": s, "hits": hits, "src": src}

pool = {}

# trending
for t in trending:
    fn = t["repo"]
    key = fn.lower()
    if key in pool:
        continue
    pool[key] = mk(fn, t.get("stars"), t.get("desc"), "", "", [], "https://github.com/" + fn,
                   forks=t.get("forks"), src="trending:" + t.get("period", ""))

# search results
for srcname, data in (("main", main), ("algo", algo)):
    for q, blob in data.items():
        for i in (blob.get("items") or []):
            fn = i.get("full_name")
            if not fn:
                continue
            key = fn.lower()
            if key in pool:
                pool[key]["src"] += "|" + q[:20]
                continue
            pool[key] = mk(fn, i.get("stars"), i.get("description"), i.get("language"),
                           i.get("created_at"), i.get("topics"), i.get("url"),
                           forks=i.get("forks"), src=q[:26])

new = [v for k, v in pool.items() if k not in seen]
new.sort(key=lambda x: (-x["score"], -(x["stars"] or 0)))

# hermes/agent-toolchain related subset
AGENT_RE = re.compile(r"agent|hermes|mcp|skill|claude|llm|copilot|tool|code assistant|orchestrat|rag", re.I)
agent_new = [x for x in new if AGENT_RE.search(x["full_name"] + " " + x["desc"] + " " + " ".join(x["topics"]))]

print(f"POOL={len(pool)} NEW={len(new)} AGENT_NEW={len(agent_new)} SEEN={len(seen)}")
json.dump(new, open("D:/hermes/analysis/new_all.json", "w", encoding="utf-8"), ensure_ascii=False)
print("\n=== TOP 15 NEW (all) ===")
for x in new[:15]:
    print(f"{x['score']:>5} ★{x['stars']} {x['full_name']} [{x['lang']}] {x['desc'][:70]}")
print("\n=== TOP 12 NEW (agent/toolchain) ===")
for x in agent_new[:12]:
    print(f"{x['score']:>5} ★{x['stars']} {x['full_name']} [{x['lang']}] {x['desc'][:70]}")
