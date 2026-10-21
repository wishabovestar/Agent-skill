# -*- coding: utf-8 -*-
"""第二波：近期(增量)查询，捕捉新项目"""
import ssl, urllib.request, urllib.parse, json, os, time

RAW = r"D:/hermes/data/agent_knowledge/algorithm/tmp"
seen = json.load(open(os.path.join(RAW, "seen.json"), encoding="utf-8"))
sr = set(x.lower() for x in seen["repos"])

def fetch(url, timeout=25):
    ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 Chrome/120","Accept":"application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", errors="ignore")

Q = [
    ("dl",        "created:>2026-07-20 topic:deep-learning stars:>200"),
    ("dl",        "created:>2026-07-20 topic:transformer stars:>150"),
    ("neural",    "created:>2026-07-20 topic:llm stars:>400"),
    ("neural",    "created:>2026-07-20 topic:llm-inference stars:>80"),
    ("neural",    "created:>2026-07-20 topic:rag stars:>300"),
    ("algorithm", "created:>2026-07-20 topic:algorithms stars:>150"),
    ("ml",        "created:>2026-07-20 topic:machine-learning stars:>200"),
    ("math",      "created:>2026-07-20 topic:optimization stars:>150"),
    ("system",    "created:>2026-07-20 topic:compiler stars:>150"),
    ("system",    "created:>2026-07-20 topic:operating-system stars:>150"),
    ("neural",    "created:>2026-07-20 kv cache llm stars:>120"),
    ("neural",    "created:>2026-07-20 attention sparse stars:>100"),
    ("dl",        "created:>2026-07-20 reasoning model stars:>300"),
    ("agent",     "created:>2026-07-20 ai agent stars:>700"),
]

new = []
errs = []
for direction, q in Q:
    url = ("https://api.github.com/search/repositories?q=" + urllib.parse.quote(q, safe=":+>") +
           "&sort=stars&order=desc&per_page=10")
    try:
        d = json.loads(fetch(url))
        its = d.get("items") or []
        if "items" not in d: errs.append((q, str(d)[:80]))
        for it in its:
            fn = it.get("full_name", "")
            new.append({"direction": direction, "query": q, "full_name": fn,
                "stars": it.get("stargazers_count", 0), "forks": it.get("forks_count", 0),
                "language": it.get("language"), "description": (it.get("description") or "")[:300],
                "created_at": it.get("created_at", ""), "pushed_at": it.get("pushed_at", ""),
                "topics": (it.get("topics") or [])[:8], "html_url": it.get("html_url", ""),
                "archived": it.get("archived", False), "is_new": fn.lower() not in sr})
    except Exception as e:
        errs.append((q, type(e).__name__ + ":" + str(e)[:70]))
    time.sleep(8)

p = os.path.join(RAW, "github_raw2.json")
json.dump(new, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("GH2_DONE items=%d new=%d errs=%d" % (len(new), sum(1 for x in new if x["is_new"]), len(errs)))
