import subprocess, json, time, urllib.parse

def gh_search(q, sort="stars", per=15):
    url = "https://api.github.com/search/repositories?q=" + urllib.parse.quote(q, safe=":+>") \
          + f"&sort={sort}&order=desc&per_page={per}"
    try:
        r = subprocess.run(["curl", "-s", "-k", "--max-time", "25", url],
                           capture_output=True, text=True, timeout=40)
        d = json.loads(r.stdout)
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
        return [], f"ERR:{type(e).__name__}"

QUERIES = [
    "topic:deep-learning created:>2026-09-11 stars:>50",
    "topic:llm created:>2026-09-11 stars:>50",
    "topic:transformer stars:>200",
    "topic:quantization stars:>30",
    "topic:fine-tuning stars:>50",
    "topic:mixture-of-experts stars:>20",
    "topic:attention stars:>30",
    "created:>2026-09-29 stars:>10",
    "topic:neural-network created:>2026-09-18 stars:>30",
    "topic:reinforcement-learning created:>2026-09-14 stars:>30",
    "topic:inference-engine created:>2026-08-18 stars:>40",
    "topic:vector-search created:>2026-08-18 stars:>40",
    "topic:rag stars:>500",
    "topic:llm-agent stars:>100",
]

result = {}
for n, q in enumerate(QUERIES):
    items, total = gh_search(q)
    result[q] = {"total": total, "items": items}
    print(f"[{n+1}/{len(QUERIES)}] {q} -> {len(items)} items (total={total})", flush=True)
    if n < len(QUERIES) - 1:
        time.sleep(7)

json.dump(result, open("D:/hermes/analysis/gh_algo.json", "w", encoding="utf-8"), ensure_ascii=False)
print("WROTE gh_algo.json")
