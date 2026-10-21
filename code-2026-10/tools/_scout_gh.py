import ssl, urllib.request, urllib.parse, json, time, os, sys

ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

OUT = r"D:/hermes/data/intel/logs/_gh_raw_20260918.json"
raw = {}

QUERIES = [
    ("mythos_claude", "Anthropic Mythos Claude"),
    ("oceanus", "Oceanus Anthropic model"),
    ("claude_leak", "claude leaked model weights"),
    ("llm_leak", "model weights leak OR model dump"),
    ("tata_electronics", "Tata Electronics"),
    ("tata_apple", "Tata Apple iPhone supply chain"),
    ("apple_supply", "apple supply chain leak"),
    ("apple_openai", "apple openai lawsuit"),
    ("recent_hot", "created:>2026-09-11 stars:>150"),
    ("recent_ai", "created:>2026-09-01 topic:llm stars:>200"),
    ("hermes_topic", "topic:hermes-agent"),
    ("agent_fw", "ai agent framework stars:>2000"),
]

def gh(q, sort="stars", per=12):
    url = ("https://api.github.com/search/repositories?q=" +
           urllib.parse.quote(q, safe=":+><") + f"&sort={sort}&order=desc&per_page={per}")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
        return json.loads(r.read().decode("utf-8", errors="ignore"))

for key, q in QUERIES:
    try:
        d = gh(q)
        items = d.get("items") or []
        raw[key] = [{"full_name": i["full_name"], "stars": i["stargazers_count"],
                     "lang": i.get("language"), "created": i.get("created_at", "")[:10],
                     "pushed": i.get("pushed_at", "")[:10], "url": i["html_url"],
                     "desc": (i.get("description") or "")[:220]} for i in items]
        print(f"[{key}] n={len(raw[key])}")
    except Exception as e:
        raw[key] = {"error": str(e)[:120]}
        print(f"[{key}] ERR {str(e)[:90]}")
    time.sleep(8)

json.dump(raw, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("saved", OUT, os.path.getsize(OUT))
