# -*- coding: utf-8 -*-
import subprocess, json, time, urllib.parse, ssl, urllib.request, os

ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
OUTDIR = "D:/hermes/analysis"

def gh_search(q, sort="stars", per=15):
    url = ("https://api.github.com/search/repositories?q=" + urllib.parse.quote(q, safe=":+>")
           + f"&sort={sort}&order=desc&per_page={per}")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
                d = json.loads(r.read().decode("utf-8", "ignore"))
            if "items" not in d:
                return [], "MSG:" + str(d.get("message", ""))[:50]
            out = []
            for i in d.get("items") or []:
                out.append({
                    "full_name": i.get("full_name"), "stars": i.get("stargazers_count"),
                    "forks": i.get("forks_count"), "language": i.get("language"),
                    "desc": (i.get("description") or "")[:240],
                    "created": i.get("created_at"), "pushed": i.get("pushed_at"),
                    "topics": i.get("topics", []), "license": (i.get("license") or {}).get("spdx_id"),
                    "url": i.get("html_url"), "size": i.get("size"),
                })
            return out, d.get("total_count")
        except Exception as e:
            if attempt == 2:
                return [], f"ERR:{type(e).__name__}:{str(e)[:50]}"
            time.sleep(5)

MAIN = [
    "ai agent tool stars:>2000",
    "mcp server stars:>500",
    "code assistant stars:>2000",
    "search engine stars:>3000",
    "cli tool stars:>2000",
    "open source ai agent stars:>2000",
    "LLM tool use agent stars:>1000",
    "topic:hermes-agent",
    "created:>2026-10-07 stars:>150",
    "topic:agent created:>2026-10-02 stars:>60",
    "topic:mcp created:>2026-09-11 stars:>60",
    "topic:agent-skills stars:>100",
    "agent harness created:>2026-09-11 stars:>80",
]
ALGO = [
    "topic:deep-learning created:>2026-10-03 stars:>40",
    "topic:llm created:>2026-10-03 stars:>40",
    "topic:transformer stars:>200",
    "topic:quantization stars:>30",
    "topic:fine-tuning stars:>50",
    "topic:mixture-of-experts stars:>20",
    "topic:attention stars:>30",
    "created:>2026-10-08 stars:>8",
    "topic:neural-network created:>2026-09-26 stars:>30",
    "topic:reinforcement-learning created:>2026-09-21 stars:>30",
    "topic:inference-engine created:>2026-08-26 stars:>40",
    "topic:vector-search created:>2026-08-26 stars:>40",
    "topic:llm-agent stars:>100",
]
SUPP = [
    "created:>2026-10-05 stars:>80",
    "created:>2026-10-07 stars:>40",
    "created:>2026-10-09 stars:>20",
    "created:>2026-10-10 stars:>15",
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
    "agent framework created:>2026-10-03 stars:>50",
    "claude code created:>2026-10-01 stars:>100",
    "agent skills created:>2026-09-26 stars:>40",
    "topic:agent created:>2026-10-05 stars:>30",
    "topic:mcp created:>2026-10-05 stars:>30",
]

ALL = [(q, "main") for q in MAIN] + [(q, "algo") for q in ALGO] + [(q, "supp") for q in SUPP]
buckets = {"main": {}, "algo": {}, "supp": {}}
log = []
for n, (q, bucket) in enumerate(ALL):
    items, total = gh_search(q)
    buckets[bucket][q] = {"total": total, "items": items}
    log.append(f"[{n+1}/{len(ALL)}] {bucket} {q} -> {len(items)} (t={total})")
    print(log[-1], flush=True)
    json.dump(buckets, open(OUTDIR + "/gh_buckets_1013.json", "w", encoding="utf-8"), ensure_ascii=False)
    if n < len(ALL) - 1:
        time.sleep(8)

json.dump(buckets, open(OUTDIR + "/gh_buckets_1013.json", "w", encoding="utf-8"), ensure_ascii=False)
json.dump(log, open(OUTDIR + "/gh_log_1013.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("DONE queries =", len(ALL))
