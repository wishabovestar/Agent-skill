import ssl, urllib.request, subprocess, json, time
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

# 1) GitHub API via curl (primary per skill)
def gh(q):
    url = "https://api.github.com/search/repositories?q=" + urllib.parse.quote(q, safe=":+>") + "&sort=stars&order=desc&per_page=3"
    r = subprocess.run(["curl","-s","-k","--max-time","20",url], capture_output=True, text=True, timeout=30)
    try:
        d = json.loads(r.stdout); return d.get("total_count"), len(d.get("items") or [])
    except Exception as e:
        return "PARSE_ERR", r.stdout[:120]

import urllib.parse
print("GH_API:", gh("topic:hermes-agent"))

# 2) rate limit
r = subprocess.run(["curl","-s","-k","--max-time","15","https://api.github.com/rate_limit"], capture_output=True, text=True, timeout=25)
try:
    d=json.loads(r.stdout)
    print("RATE search:", d["resources"]["search"]["remaining"], "/", d["resources"]["search"]["limit"],
          "core:", d["resources"]["core"]["remaining"])
except Exception as e:
    print("RATE_ERR", r.stdout[:100])

# 3) trending local probe (short timeout)
try:
    req = urllib.request.Request("https://github.com/trending?since=daily",
        headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req, timeout=12, context=ctx) as r2:
        h = r2.read().decode("utf-8","replace")
    print("TRENDING_LOCAL: OK bytes=%d cards=%d" % (len(h), h.count('<article class="Box-row">')))
except Exception as e:
    print("TRENDING_LOCAL: FAIL", type(e).__name__, str(e)[:80])
