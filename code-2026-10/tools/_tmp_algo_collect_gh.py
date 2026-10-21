# -*- coding: utf-8 -*-
"""巡天 GitHub 采集 (算法/数学/系统/DL/ML/神经)"""
import ssl, urllib.request, urllib.parse, json, os, time

BASE = r"D:/hermes/data/agent_knowledge"
RAW = os.path.join(BASE, "algorithm", "tmp")
os.makedirs(RAW, exist_ok=True)

def fetch(url, timeout=25):
    ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    req = urllib.request.Request(url, headers={
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
        "Accept":"application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", errors="ignore")

QUERIES = [
    ("algorithm", "topic:algorithm stars:>3000"),
    ("algorithm", "topic:dynamic-programming stars:>300"),
    ("math",      "topic:optimization stars:>2000"),
    ("math",      "topic:linear-algebra stars:>800"),
    ("system",    "topic:operating-system stars:>3000"),
    ("system",    "topic:compiler stars:>1500"),
    ("dl",        "topic:deep-learning stars:>5000"),
    ("ml",        "topic:machine-learning stars:>5000"),
    ("neural",    "topic:llm stars:>5000"),
    ("neural",    "topic:transformer stars:>1500"),
    ("hotspot",   "created:>2026-08-25 stars:>1500"),
    ("hotspot",   "created:>2026-09-05 stars:>400"),
    ("neural",    "llm agent framework stars:>2000"),
]

out = []
errs = []
for direction, q in QUERIES:
    url = ("https://api.github.com/search/repositories?q=" +
           urllib.parse.quote(q, safe=":+>") +
           "&sort=stars&order=desc&per_page=10")
    for attempt in range(3):
        try:
            txt = fetch(url)
            d = json.loads(txt)
            if "items" not in d:
                errs.append((q, str(d)[:100]))
                break
            for it in (d.get("items") or []):
                out.append({
                    "direction": direction, "query": q,
                    "full_name": it.get("full_name"),
                    "stars": it.get("stargazers_count", 0),
                    "forks": it.get("forks_count", 0),
                    "language": it.get("language"),
                    "description": (it.get("description") or "")[:300],
                    "created_at": it.get("created_at", ""),
                    "pushed_at": it.get("pushed_at", ""),
                    "topics": (it.get("topics") or [])[:8],
                    "html_url": it.get("html_url", ""),
                    "archived": it.get("archived", False),
                })
            break
        except Exception as e:
            msg = str(e)[:80]
            if "403" in msg or "rate" in msg.lower():
                time.sleep(25); continue
            errs.append((q, type(e).__name__ + ":" + msg)); break
    time.sleep(8)

json.dump(out, open(os.path.join(RAW, "github_raw.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(errs, open(os.path.join(RAW, "github_errs.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("GH_DONE items=%d errs=%d" % (len(out), len(errs)))
