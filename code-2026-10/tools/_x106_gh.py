import subprocess, json, time, sys, urllib.parse

def gh_search(q, sort="stars", per=15):
    url = "https://api.github.com/search/repositories?q=" + urllib.parse.quote(q, safe=":+>") \
          + f"&sort={sort}&order=desc&per_page={per}"
    for attempt in range(2):
        try:
            r = subprocess.run(["curl","-s","-k","--max-time","25",url],
                               capture_output=True, text=True, timeout=40)
            d = json.loads(r.stdout)
            if "items" not in d and d.get("message"):
                return [], "RATELIMIT:" + str(d.get("message"))[:40]
            items = d.get("items") or []
            out = []
            for i in items:
                out.append({
                    "full_name": i.get("full_name"), "stars": i.get("stargazers_count"),
                    "forks": i.get("forks_count"), "language": i.get("language"),
                    "description": (i.get("description") or "")[:240],
                    "created_at": i.get("created_at"), "pushed_at": i.get("pushed_at"),
                    "topics": i.get("topics", []), "license": (i.get("license") or {}).get("spdx_id"),
                    "url": i.get("html_url"),
                })
            return out, d.get("total_count")
        except Exception as e:
            if attempt == 1:
                return [], f"ERR:{type(e).__name__}"
            time.sleep(3)

MAIN = [
    "open source ai agent stars:>2000",
    "LLM tool use agent stars:>1000",
    "code assistant stars:>2000",
    "cli tool stars:>2000",
    "mcp server stars:>500",
    "search engine stars:>3000",
    "topic:hermes-agent",
    "created:>2026-10-01 stars:>150",
    "topic:agent created:>2026-09-26 stars:>60",
    "topic:mcp created:>2026-09-06 stars:>60",
    "topic:agent-skills stars:>100",
    "claude skills created:>2026-09-06 stars:>80",
    "agent harness created:>2026-09-06 stars:>80",
    "created:>2026-10-01 stars:>40",
    "created:>2026-09-29 stars:>20",
]
ALGO = [
    "topic:deep-learning created:>2026-09-27 stars:>40",
    "topic:llm created:>2026-09-27 stars:>40",
    "topic:transformer stars:>200",
    "topic:quantization stars:>30",
    "topic:fine-tuning stars:>50",
    "topic:mixture-of-experts stars:>20",
    "topic:attention stars:>30",
    "created:>2026-10-02 stars:>8",
    "topic:neural-network created:>2026-09-18 stars:>30",
    "topic:reinforcement-learning created:>2026-09-14 stars:>30",
    "topic:inference-engine created:>2026-08-18 stars:>40",
    "topic:vector-search created:>2026-08-18 stars:>40",
    "topic:rag stars:>500",
    "topic:llm-agent stars:>100",
]
SUPP = [
    "created:>2026-09-29 stars:>80",
    "created:>2026-10-01 stars:>40",
    "created:>2026-10-03 stars:>20",
    "created:>2026-10-04 stars:>15",
    "topic:ai-agent stars:>40",
    "topic:mcp-server stars:>40",
    "topic:agentic-ai stars:>40",
    "topic:coding-agent stars:>40",
    "topic:claude-code stars:>40",
    "topic:hermes stars:>20",
    "topic:agent-memory stars:>50",
    "topic:context-engineering stars:>50",
    "topic:computer-use stars:>50",
    "topic:token-optimization stars:>30",
    "topic:agent-orchestration stars:>50",
    "topic:multi-agent stars:>40",
    "topic:llm-inference stars:>40",
    "agent framework created:>2026-09-27 stars:>50",
    "claude code created:>2026-09-25 stars:>100",
    "agent skills created:>2026-09-20 stars:>40",
    "topic:agent created:>2026-09-29 stars:>30",
    "topic:mcp created:>2026-09-29 stars:>30",
    "created:>2026-09-22 stars:>200",
    "topic:terminal stars:>100 created:>2026-08-01",
]

ALL = [(q, "main") for q in MAIN] + [(q, "algo") for q in ALGO] + [(q, "supp") for q in SUPP]
buckets = {"main": {}, "algo": {}, "supp": {}}
log = []
for n, (q, bucket) in enumerate(ALL):
    items, total = gh_search(q)
    buckets[bucket][q] = {"total": total, "items": items}
    log.append(f"[{n+1}/{len(ALL)}] {bucket} {q} -> {len(items)} (t={total})")
    print(log[-1], flush=True)
    # incremental save
    json.dump(buckets, open("D:/hermes/analysis/gh_buckets_1006.json","w",encoding="utf-8"), ensure_ascii=False)
    if n < len(ALL) - 1:
        time.sleep(7)

json.dump(buckets["main"], open("D:/hermes/analysis/gh_main.json","w",encoding="utf-8"), ensure_ascii=False)
json.dump(buckets["algo"], open("D:/hermes/analysis/gh_algo.json","w",encoding="utf-8"), ensure_ascii=False)
json.dump(buckets["supp"], open("D:/hermes/analysis/gh_supp.json","w",encoding="utf-8"), ensure_ascii=False)
json.dump(log, open("D:/hermes/analysis/gh_log_1006.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("DONE queries =", len(ALL))
