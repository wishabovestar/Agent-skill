import ssl, urllib.request, urllib.parse, json, time, os, re
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
HDR={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
     "Accept":"application/json, text/html;q=0.9","Accept-Language":"en-US,en;q=0.9"}
def get(url, to=25, accept=None):
    h=dict(HDR)
    if accept: h["Accept"]=accept
    req=urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=to, context=ctx) as r:
        return r.read().decode("utf-8", errors="ignore")

OUT="D:/hermes/data/agent_knowledge/算法"
os.makedirs("D:/hermes/analysis/_xt0923", exist_ok=True)
res={"trending":[], "search":{}, "errors":[]}

# ---------- 1. GitHub Trending (daily/weekly) ----------
for period in ("daily","weekly"):
    got=False
    for attempt in (1,2):
        try:
            html=get(f"https://github.com/trending?since={period}", to=20)
            open(f"D:/hermes/analysis/_xt0923/trending_{period}.html","w",encoding="utf-8").write(html)
            print(f"TREND {period} local OK {len(html)}")
            got=True; break
        except Exception as e:
            print(f"TREND {period} local FAIL {type(e).__name__}")
            time.sleep(2)
    if not got:
        res["errors"].append(f"trending_{period}_local_fail")

# ---------- 2. GitHub Search ----------
QUERIES = [
    ("ai_agent",     "ai+agent+tool+stars:%3E500"),
    ("mcp_server",   "mcp+server+stars:%3E300"),
    ("code_assist",  "code+assistant+stars:%3E1000"),
    ("search_engine","search+engine+stars:%3E500"),
    ("cli_tool",     "cli+tool+stars:%3E800"),
    ("hermes_topic", "topic:hermes-agent"),
    ("new_agents",   "agent+created:%3E2026-08-24+stars:%3E100"),
    ("new_llm",      "llm+created:%3E2026-08-24+stars:%3E150"),
]
for name,q in QUERIES:
    try:
        url=f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=15"
        d=json.loads(get(url, to=25))
        items=d.get("items") or []
        res["search"][name]=[{
            "full_name":i["full_name"], "stars":i["stargazers_count"],
            "language":i.get("language") or "N/A",
            "description":(i.get("description") or "")[:300],
            "topics":(i.get("topics") or [])[:12],
            "created_at":i.get("created_at","")[:10],
            "pushed_at":i.get("pushed_at","")[:10],
            "url":i.get("html_url",""), "forks":i.get("forks_count",0),
            "total_count":d.get("total_count",0)
        } for i in items]
        print(f"GH {name} OK n={len(items)} total={d.get('total_count',0)}")
    except Exception as e:
        print(f"GH {name} FAIL {type(e).__name__} {str(e)[:60]}")
        res["errors"].append(f"gh_{name}: {str(e)[:60]}")
    time.sleep(8)

# ---------- 3. Algorithm / DL / NN 专项 ----------
ALGO = [
    ("dl_new",     "deep+learning+created:%3E2026-08-16+stars:%3E50"),
    ("nn_new",     "neural+network+created:%3E2026-08-16+stars:%3E50"),
    ("algo_topic", "topic:algorithms+stars:%3E300"),
    ("transformer","transformer+created:%3E2026-08-01+stars:%3E100"),
    ("agent_algo", "topic:llm+created:%3E2026-08-16+stars:%3E100"),
]
for name,q in ALGO:
    try:
        url=f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=15"
        d=json.loads(get(url, to=25))
        items=d.get("items") or []
        res["search"][name]=[{
            "full_name":i["full_name"], "stars":i["stargazers_count"],
            "language":i.get("language") or "N/A",
            "description":(i.get("description") or "")[:300],
            "topics":(i.get("topics") or [])[:12],
            "created_at":i.get("created_at","")[:10],
            "pushed_at":i.get("pushed_at","")[:10],
            "url":i.get("html_url",""), "forks":i.get("forks_count",0),
            "total_count":d.get("total_count",0)
        } for i in items]
        print(f"ALGO {name} OK n={len(items)} total={d.get('total_count',0)}")
    except Exception as e:
        print(f"ALGO {name} FAIL {type(e).__name__} {str(e)[:60]}")
        res["errors"].append(f"algo_{name}: {str(e)[:60]}")
    time.sleep(8)

json.dump(res, open("D:/hermes/analysis/_xt0923/raw_0923.json","w",encoding="utf-8"), ensure_ascii=False)
tot=sum(len(v) for v in res["search"].values())
print(f"SAVED raw_0923.json search_items={tot} errors={len(res['errors'])}")
