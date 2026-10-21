import subprocess, json, time, urllib.parse

def gh_search(q, per=15):
    url = "https://api.github.com/search/repositories?q=" + urllib.parse.quote(q, safe=":+>") \
          + f"&sort=stars&order=desc&per_page={per}"
    try:
        r = subprocess.run(["curl", "-s", "-k", "--max-time", "25", url],
                           capture_output=True, text=True, timeout=40)
        d = json.loads(r.stdout)
        items = d.get("items") or []
        return [{"full_name": i.get("full_name"), "stars": i.get("stargazers_count"),
                 "forks": i.get("forks_count"), "language": i.get("language"),
                 "description": (i.get("description") or "")[:240],
                 "created_at": i.get("created_at"), "pushed_at": i.get("pushed_at"),
                 "topics": i.get("topics", []), "license": (i.get("license") or {}).get("spdx_id"),
                 "url": i.get("html_url")} for i in items], d.get("total_count")
    except Exception as e:
        return [], f"ERR:{type(e).__name__}"

QUERIES = [
    "created:>2026-09-27 stars:>40",
    "created:>2026-09-30 stars:>15",
    "created:>2026-09-23 stars:>60",
    "topic:ai-agent stars:>40",
    "topic:mcp-server stars:>40",
    "topic:agentic-ai stars:>40",
    "topic:coding-agent stars:>40",
    "topic:claude-code stars:>40",
    "topic:hermes stars:>20",
    "topic:agent-skills created:>2026-09-01 stars:>50",
    "agent stars:>40 created:>2026-09-20",
    "llm stars:>40 created:>2026-09-20",
    "mcp stars:>30 created:>2026-09-20",
    "skill stars:>50 created:>2026-09-15",
    "topic:llm-inference stars:>40",
    "topic:autonomous-agents stars:>40",
    "topic:multi-agent stars:>40",
    "created:>2026-09-27 stars:>30",
    "topic:deep-learning stars:>300",
    "topic:neural-networks stars:>40",
    "topic:large-language-model stars:>100",
    "topic:diffusion-models stars:>100",
    "topic:machine-learning stars:>500",
    "topic:openai stars:>100",
]

result = {}
for n, q in enumerate(QUERIES):
    items, total = gh_search(q)
    result[q] = {"total": total, "items": items}
    print(f"[{n+1}/{len(QUERIES)}] {q} -> {len(items)} (t={total})", flush=True)
    if n < len(QUERIES) - 1:
        time.sleep(7)

json.dump(result, open("D:/hermes/analysis/gh_supp.json", "w", encoding="utf-8"), ensure_ascii=False)
print("WROTE gh_supp.json")
