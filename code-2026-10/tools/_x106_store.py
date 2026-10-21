import json, re, os, datetime

DATE = "2026-10-06"
new = json.load(open("D:/hermes/analysis/new_all.json", encoding="utf-8"))
trending = json.load(open("D:/hermes/analysis/trending_parsed.json", encoding="utf-8"))
main = json.load(open("D:/hermes/analysis/gh_main.json", encoding="utf-8"))
algo = json.load(open("D:/hermes/analysis/gh_algo.json", encoding="utf-8"))
supp = json.load(open("D:/hermes/analysis/gh_supp.json", encoding="utf-8"))
seen = json.load(open("D:/hermes/analysis/seen_repos.json", encoding="utf-8"))
pool = json.load(open("D:/hermes/analysis/gh_buckets_1006.json", encoding="utf-8"))

ALGO_RE = re.compile(r"deep.?learn|neural|transformer|llm|language model|pytorch|tensorflow|quantiz|"
                     r"fine.?tun|mixture.?of.?experts|moe|attention|inference|diffusion|reinforcement|"
                     r"embedding|vector|rag|machine.?learn|training|gpt|foundation model", re.I)
algo_topics = {"deep-learning","llm","transformer","quantization","fine-tuning","mixture-of-experts",
               "attention","neural-network","neural-networks","reinforcement-learning","inference-engine",
               "vector-search","rag","large-language-model","diffusion-models","machine-learning","openai",
               "llm-agent","pytorch"}

def is_algo(x):
    blob = (x["full_name"] + " " + x["desc"] + " " + " ".join(x["topics"] or []))
    if set(t.lower() for t in (x["topics"] or [])) & algo_topics:
        return True
    return bool(ALGO_RE.search(blob))

algo_new = [x for x in new if is_algo(x)]
AGENT_FIRST = re.compile(r"agent|mcp|skill|claude|code assist|harness|gateway|memory", re.I)
for x in list(algo_new):
    if AGENT_FIRST.search(x["full_name"] + " " + x["desc"]):
        algo_new.remove(x)
agent_new = [x for x in new if x not in algo_new]
algo_new.sort(key=lambda x: -x["score"])
agent_new.sort(key=lambda x: -x["score"])

# top10 high-value agent/toolchain; require score>=3 else fall back
top10 = [x for x in agent_new if x["score"] >= 3][:10]
if len(top10) < 10:
    top10 = agent_new[:10]

pool_size = sum(len(v.get("items") or []) for b in pool.values() for v in b.values())

report = {
    "date": DATE,
    "generated": datetime.datetime.now().isoformat(timespec="seconds"),
    "scout": "xuntian-github-scout v3.6",
    "queries_total": len(main) + len(algo) + len(supp),
    "seen_repos": len(seen),
    "pool": pool_size,
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

algo_ext = {"date": DATE, "generated": report["generated"],
            "source": "xuntian-github-scout extended (algo/DL/NN)",
            "count": len(algo_new), "repos": algo_new}
p2 = f"{outdir}/algo_ext_{DATE}.json"
json.dump(algo_ext, open(p2, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

logpath = f"{outdir}/_collection_log.json"
try:
    lg = json.load(open(logpath, encoding="utf-8"))
    if not isinstance(lg, list): lg = [lg]
except Exception:
    lg = []
lg.append({"date": DATE, "scout": "xuntian-github-scout v3.6", "pool": pool_size,
           "new": len(new), "agent_new": len(agent_new), "algo_new": len(algo_new),
           "files": [os.path.basename(p1), os.path.basename(p2)]})
json.dump(lg, open(logpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("WROTE", os.path.basename(p1), os.path.getsize(p1), "bytes")
print("WROTE", os.path.basename(p2), os.path.getsize(p2), "bytes")
print("LOG entries", len(lg))
print("TOP10:")
for n, x in enumerate(top10, 1):
    print(f"  {n}. {x['full_name']} *{x['stars']} score={x['score']} [{x.get('lang')}]")
