import subprocess, json, time, sys, urllib.parse

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
                "full_name": i.get("full_name"),
                "stars": i.get("stargazers_count"),
                "forks": i.get("forks_count"),
                "language": i.get("language"),
                "description": (i.get("description") or "")[:240],
                "created_at": i.get("created_at"),
                "pushed_at": i.get("pushed_at"),
                "topics": i.get("topics", []),
                "license": (i.get("license") or {}).get("spdx_id"),
                "url": i.get("html_url"),
            })
        return out, d.get("total_count")
    except Exception as e:
        return [], f"ERR:{type(e).__name__}:{str(e)[:60]}"

QUERIES = sys.argv[1:] if len(sys.argv) > 1 else []
if not QUERIES:
    QUERIES = [
        "open source ai agent stars:>2000",
        "LLM tool use agent stars:>1000",
        "code assistant stars:>2000",
        "cli tool stars:>2000",
        "mcp server stars:>500",
        "search engine stars:>3000",
        "topic:hermes-agent",
        "created:>2026-09-05 stars:>300",
        "topic:agent created:>2026-09-02 stars:>80",
        "topic:mcp created:>2026-08-18 stars:>80",
        "topic:agent-skills stars:>100",
        "claude skills created:>2026-08-18 stars:>100",
        "agent harness created:>2026-08-18 stars:>80",
        "created:>2026-09-25 stars:>80",
        "created:>2026-09-21 stars:>40",
    ]

result = {}
for n, q in enumerate(QUERIES):
    items, total = gh_search(q)
    result[q] = {"total": total, "items": items}
    print(f"[{n+1}/{len(QUERIES)}] {q} -> {len(items)} items (total={total})", flush=True)
    if n < len(QUERIES) - 1:
        time.sleep(7)

json.dump(result, open("D:/hermes/analysis/gh_main.json", "w", encoding="utf-8"), ensure_ascii=False)
print("WROTE gh_main.json")
