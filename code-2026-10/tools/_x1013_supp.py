# -*- coding: utf-8 -*-
import json, time, urllib.parse, ssl, urllib.request

ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
OUT = "D:/hermes/analysis/gh_buckets_1013.json"

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
                out.append({"full_name": i.get("full_name"), "stars": i.get("stargazers_count"),
                            "forks": i.get("forks_count"), "language": i.get("language"),
                            "desc": (i.get("description") or "")[:240],
                            "created": i.get("created_at"), "pushed": i.get("pushed_at"),
                            "topics": i.get("topics", []), "license": (i.get("license") or {}).get("spdx_id"),
                            "url": i.get("html_url"), "size": i.get("size")})
            return out, d.get("total_count")
        except Exception as e:
            if attempt == 2:
                return [], f"ERR:{type(e).__name__}:{str(e)[:50]}"
            time.sleep(5)

SUPP = [
    "created:>2026-10-10 stars:>30",
    "created:>2026-10-11 stars:>10",
    "created:>2026-10-09 stars:>50",
    "topic:agent created:>2026-10-06 stars:>20",
    "topic:mcp created:>2026-10-06 stars:>20",
    "topic:agent-skills created:>2026-09-20 stars:>30",
    "claude skills created:>2026-09-20 stars:>40",
    "agent harness created:>2026-09-20 stars:>40",
    "topic:ai-agent created:>2026-09-25 stars:>30",
    "topic:coding-agent created:>2026-09-25 stars:>30",
    "topic:llm created:>2026-10-05 stars:>20",
    "topic:deep-learning created:>2026-10-05 stars:>20",
    "topic:transformer created:>2026-09-25 stars:>20",
    "topic:reinforcement-learning created:>2026-09-25 stars:>15",
    "topic:neural-network stars:>50",
    "topic:attention created:>2026-09-25 stars:>20",
]

buckets = json.load(open(OUT, encoding="utf-8"))
if "supl" not in buckets:
    buckets["supl"] = {}
log = []
for n, q in enumerate(SUPP):
    items, total = gh_search(q)
    buckets["supl"][q] = {"total": total, "items": items}
    log.append(f"[{n+1}/{len(SUPP)}] supl {q} -> {len(items)} (t={total})")
    print(log[-1], flush=True)
    json.dump(buckets, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    if n < len(SUPP) - 1:
        time.sleep(8)

json.dump(buckets, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print("SUPP DONE =", len(SUPP))
