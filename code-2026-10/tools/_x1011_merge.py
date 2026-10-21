# -*- coding: utf-8 -*-
import json, os, glob, re, datetime

DATE = "2026-10-11"
buckets = json.load(open("D:/hermes/analysis/gh_buckets_1011.json", encoding="utf-8"))
trending = json.load(open("D:/hermes/data/agent_knowledge/算法/tmp/trending_parsed_1011.json", encoding="utf-8"))

# ---------- relevance keywords ----------
KW = {"agent harness":5,"harness":2,"agent skills":3,"agent skill":3,"claude code":3,"claude":2,"mcp":3,
      "multi-agent":3,"multi agent":3,"orchestrat":4,"agent memory":3,"memory runtime":3,"self-improv":3,
      "agentic":2,"skil":2,"code review":2,"compress":2,"tool use":2,"tool router":4,"tool-calling":3,
      "rag":1,"continual learning":2,"coding agent":3,"coding-agent":3,"local-first":1,"deep learning":1,
      "neural":1,"reinforcement learning":1,"inference":2,"vector search":1,"llm":2,"agent":3,
      "context engineering":3,"token":2,"computer use":3,"terminal":1,"cli":1,"gpt":1,"copilot":2,
      "openai":1,"automation":1,"workflow":1,"prompt":2,"gateway":2,"personal assistant":2,"assistant":1,
      "framework":1,"sandbox":1,"security":1,"browser":1,"embedding":1,"fine-tun":2,"transformer":2}

def rel(nm, desc, topics):
    t = (nm + " " + (desc or "") + " " + " ".join(topics or [])).lower()
    s = 0
    for k, v in KW.items():
        if k in t:
            s += v
    return min(10, s)

def star_coef(st):
    if st >= 3000: return 1.0
    if st >= 1000: return 0.9
    if st >= 300: return 0.78
    if st >= 100: return 0.65
    return 0.5

# ---------- seen set (recursive) ----------
SEEN_ROOTS = ["D:/hermes/data/agent_knowledge", "D:/hermes/data/math_knowledge",
              "D:/hermes/data/book_knowledge", "D:/hermes/data/physics_knowledge",
              "D:/hermes/data/intel"]
seen = set()
files = 0
for root in SEEN_ROOTS:
    for f in glob.glob(root + "/**/*.json", recursive=True):
        fp = f.replace("\\", "/")
        base = os.path.basename(fp)
        if "/tmp/" in fp or base.startswith("_") or DATE in fp:
            continue
        files += 1
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for m in re.finditer(r'github\.com/([A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+)', txt):
            seen.add(m.group(1).lower())
        try:
            d = json.loads(txt)
        except Exception:
            d = None
        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in ("full_name", "repo", "name") and isinstance(v, str) and "/" in v:
                        seen.add(v.split("github.com/")[-1].strip("/").lower())
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        if d is not None:
            walk(d)

# ---------- merge all search items ----------
byname = {}
src_label = {}
for bucket, qmap in buckets.items():
    for q, obj in qmap.items():
        for it in (obj.get("items") or []):
            k = it.get("full_name")
            if not k:
                continue
            if k in byname:
                byname[k]["stars"] = max(byname[k]["stars"], it.get("stars") or 0)
                if q not in byname[k]["source"]:
                    byname[k]["source"].append(q)
            else:
                byname[k] = {"full_name": k, "stars": it.get("stars") or 0, "forks": it.get("forks") or 0,
                             "language": it.get("language") or "", "description": it.get("desc") or "",
                             "topics": it.get("topics") or [], "created_at": it.get("created") or "",
                             "pushed_at": it.get("pushed") or "", "url": it.get("url") or ("https://github.com/" + k),
                             "license": it.get("license") or "N/A", "source": [q], "period_gain": 0}

# merge trending (add if new)
for it in trending:
    k = it["repo"]
    if k not in byname:
        byname[k] = {"full_name": k, "stars": it.get("stars") or 0, "forks": it.get("forks") or 0,
                     "language": it.get("lang") or "", "description": it.get("desc") or "",
                     "topics": [], "created_at": "", "pushed_at": "",
                     "url": "https://github.com/" + k, "license": "N/A",
                     "source": ["trending_" + it.get("period", "")], "period_gain": it.get("period_gain") or 0}
    else:
        byname[k]["period_gain"] = max(byname[k].get("period_gain", 0), it.get("period_gain") or 0)
        byname[k]["stars"] = max(byname[k]["stars"], it.get("stars") or 0)
        if "trending_" + it.get("period", "") not in byname[k]["source"]:
            byname[k]["source"].append("trending_" + it.get("period", ""))

items = list(byname.values())
for it in items:
    it["is_new"] = it["full_name"].lower() not in seen
    it["relevance"] = rel(it["full_name"], it.get("description"), it.get("topics"))
    it["score"] = round(it["relevance"] * star_coef(it["stars"]), 2)

# ---------- classify ----------
ALGO_RE = re.compile(r"deep.?learn|neural|transformer|llm|language model|pytorch|tensorflow|quantiz|"
                     r"fine.?tun|mixture.?of.?experts|\bmoe\b|attention|inference|diffusion|reinforcement|"
                     r"embedding|vector|rag|machine.?learn|training|gpt|foundation model|speech|asr|"
                     r"vision|segmentation|cnn|diffusion|reinforcement|optimization|gradient|"
                     r"dataset|benchmark|diffusion", re.I)
algo_topics = {"deep-learning","llm","transformer","quantization","fine-tuning","mixture-of-experts",
               "attention","neural-network","neural-networks","reinforcement-learning","inference-engine",
               "vector-search","rag","large-language-model","diffusion-models","machine-learning","openai",
               "llm-agent","pytorch","tensorflow","computer-vision","nlp","speech-recognition"}
AGENT_FIRST = re.compile(r"agent|mcp|skill|claude|code assist|harness|gateway|memory|assistant", re.I)

def is_algo(x):
    ts = set(t.lower() for t in (x.get("topics") or []))
    if ts & algo_topics:
        return True
    return bool(ALGO_RE.search(x["full_name"] + " " + (x.get("description") or "")))

new = [x for x in items if x["is_new"]]
algo_new = [x for x in new if is_algo(x) and not AGENT_FIRST.search(x["full_name"])]
# agent_new = remaining new
algo_ids = set(id(x) for x in algo_new)
agent_new = [x for x in new if id(x) not in algo_ids]
algo_new.sort(key=lambda x: -x["score"])
agent_new.sort(key=lambda x: -x["score"])

trend_sorted = sorted(trending, key=lambda z: -(z.get("stars") or 0))
pool_size = sum(len(v.get("items") or []) for b in buckets.values() for v in b.values())

report = {
    "date": DATE, "generated": datetime.datetime.now().isoformat(timespec="seconds"),
    "scout": "xuntian-github-scout v3.6",
    "queries_total": sum(len(b) for b in buckets.values()),
    "seen_repos": len(seen), "pool": pool_size, "unique_repos": len(items),
    "new_count": len(new), "agent_new_count": len(agent_new), "algo_new_count": len(algo_new),
    "trending_count": len(trending),
    "new_all": sorted(new, key=lambda x: -x["score"]),
    "top10": (([x for x in agent_new if x["relevance"] >= 3] or agent_new))[:10],
    "trending": trend_sorted,
    "queries": {k: v.get("total") for b in buckets.values() for k, v in b.items()},
}
outdir = "D:/hermes/data/agent_knowledge/算法"
os.makedirs(outdir, exist_ok=True)
p1 = f"{outdir}/xuntian_github_scout_{DATE}.json"
json.dump(report, open(p1, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

algo_ext = {"date": DATE, "generated": report["generated"],
            "source": "xuntian-github-scout extended (algo/DL/NN)",
            "count": len(algo_new), "repos": algo_new,
            "algo_top": sorted(algo_new, key=lambda x: -x["stars"])[:30]}
p2 = f"{outdir}/algo_ext_{DATE}.json"
json.dump(algo_ext, open(p2, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

p3 = f"{outdir}/github_algo_scout_{DATE}.json"
json.dump({"date": DATE, "generated": report["generated"], "count": len(algo_new),
           "items": algo_new}, open(p3, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

logpath = f"{outdir}/_collection_log.json"
try:
    lg = json.load(open(logpath, encoding="utf-8"))
    if not isinstance(lg, list): lg = lg.get("entries", []) if isinstance(lg, dict) else [lg]
except Exception:
    lg = []
lg.append({"date": DATE, "scout": "xuntian-github-scout v3.6", "seen": len(seen), "pool": pool_size,
           "new": len(new), "agent_new": len(agent_new), "algo_new": len(algo_new),
           "files": [os.path.basename(p1), os.path.basename(p2), os.path.basename(p3)]})
json.dump(lg, open(logpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

json.dump({"seen": len(seen), "files_scanned": files, "new": len(new), "algo_new": len(algo_new),
           "agent_new": len(agent_new), "pool": pool_size, "unique": len(items)},
          open("D:/hermes/analysis/x1011_stats.json", "w", encoding="utf-8"), ensure_ascii=False)

print("STATS: files=%d seen=%d pool=%d unique=%d NEW=%d agent_new=%d algo_new=%d trending=%d"
      % (files, len(seen), pool_size, len(items), len(new), len(agent_new), len(algo_new), len(trending)))
print("WROTE", os.path.basename(p1), os.path.getsize(p1), os.path.basename(p2), os.path.getsize(p2))
print("AGENT_NEW_TOP:")
for x in agent_new[:12]:
    print("  %s|*%d|rel%d|score%.1f|%s|%s|%s" % (x["full_name"], x["stars"], x["relevance"], x["score"],
          x.get("language") or "-", (x.get("created_at") or "")[:10], (x.get("description") or "")[:70]))
print("ALGO_NEW_TOP:")
for x in algo_new[:12]:
    print("  %s|*%d|rel%d|score%.1f|%s|%s|%s" % (x["full_name"], x["stars"], x["relevance"], x["score"],
          x.get("language") or "-", (x.get("created_at") or "")[:10], (x.get("description") or "")[:70]))
