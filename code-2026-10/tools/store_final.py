import json, re, os, datetime

DATE = "2026-10-02"
new = json.load(open("D:/hermes/analysis/new_all.json", encoding="utf-8"))
trending = json.load(open("D:/hermes/analysis/trending_parsed.json", encoding="utf-8"))
main = json.load(open("D:/hermes/analysis/gh_main.json", encoding="utf-8"))
algo = json.load(open("D:/hermes/analysis/gh_algo.json", encoding="utf-8"))
supp = json.load(open("D:/hermes/analysis/gh_supp.json", encoding="utf-8"))

# ---------- algo / DL / NN classification ----------
ALGO_RE = re.compile(r"deep.?learn|neural|transformer|llm|language model|pytorch|tensorflow|quantiz|"
                     r"fine.?tun|mixture.?of.?experts|moe|attention|inference|diffusion|reinforcement|"
                     r"embedding|vector|rag|machine.?learn|training|gpt|foundation model", re.I)
algo_topics = {"deep-learning", "llm", "transformer", "quantization", "fine-tuning",
               "mixture-of-experts", "attention", "neural-network", "neural-networks",
               "reinforcement-learning", "inference-engine", "vector-search", "rag",
               "large-language-model", "diffusion-models", "machine-learning", "openai",
               "llm-agent", "pytorch"}

def is_algo(x):
    blob = (x["full_name"] + " " + x["desc"] + " " + " ".join(x["topics"] or []))
    if set(t.lower() for t in (x["topics"] or [])) & algo_topics:
        return True
    return bool(ALGO_RE.search(blob))

algo_new = [x for x in new if is_algo(x)]
algo_new.sort(key=lambda x: -x["score"])
agent_new = [x for x in new if not is_algo(x)]
# re-add strong agent ones that got caught by 'llm' keyword but are agent-first
AGENT_FIRST = re.compile(r"agent|mcp|skill|claude|code assist|harness|gateway|memory", re.I)
for x in list(algo_new):
    if AGENT_FIRST.search(x["full_name"] + " " + x["desc"]):
        algo_new.remove(x)
        agent_new.append(x)
agent_new.sort(key=lambda x: -x["score"])

# ---------- top10 high value (agent/toolchain; prefer new, allow notable) ----------
top10 = agent_new[:10]

report = {
    "date": DATE,
    "generated": datetime.datetime.now().isoformat(timespec="seconds"),
    "scout": "xuntian-github-scout v3.6",
    "queries_total": len(main) + len(algo) + len(supp),
    "seen_repos": 2842,
    "pool": 546,
    "new_count": len(new),
    "agent_new_count": len(agent_new),
    "algo_new_count": len(algo_new),
    "trending_count": len(trending),
    "top10": top10,
    "new_all": new,
    "trending": sorted(trending, key=lambda z: -(z.get("stars") or 0)),
    "queries": {k: v.get("total") for k, v in {**main, **algo, **supp}.items()},
}

outdir = "D:/hermes/data/agent_knowledge/算法"
os.makedirs(outdir, exist_ok=True)
p1 = f"{outdir}/xuntian_github_scout_{DATE}.json"
json.dump(report, open(p1, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

algo_ext = {
    "date": DATE,
    "generated": report["generated"],
    "source": "xuntian-github-scout extended (algo/DL/NN)",
    "count": len(algo_new),
    "repos": algo_new,
}
p2 = f"{outdir}/algo_ext_{DATE}.json"
json.dump(algo_ext, open(p2, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------- collection log ----------
logpath = f"{outdir}/_collection_log.json"
try:
    log = json.load(open(logpath, encoding="utf-8"))
    if not isinstance(log, list):
        log = [log]
except Exception:
    log = []
log.append({"date": DATE, "scout": "xuntian-github-scout v3.6",
            "pool": 546, "new": len(new), "agent_new": len(agent_new), "algo_new": len(algo_new),
            "files": [os.path.basename(p1), os.path.basename(p2)]})
json.dump(log, open(logpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("WROTE", p1, os.path.getsize(p1), "bytes")
print("WROTE", p2, os.path.getsize(p2), "bytes")
print("LOG", logpath, "entries", len(log))
print("TOP10:")
for n, x in enumerate(top10, 1):
    print(f"  {n}. {x['full_name']} ★{x['stars']} score={x['score']}")
