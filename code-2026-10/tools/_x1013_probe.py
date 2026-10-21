# -*- coding: utf-8 -*-
import ssl, urllib.request, urllib.parse, subprocess, json, time, os
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

def gh_api(url, tries=4):
    last=""
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
                return json.loads(r.read().decode("utf-8", "ignore"))
        except Exception as e:
            last = f"{type(e).__name__}:{str(e)[:70]}"
            time.sleep(4)
    return {"__err__": last}

d = gh_api("https://api.github.com/search/repositories?q=topic:hermes-agent&sort=stars&order=desc&per_page=3")
print("GH_SEARCH total:", d.get("total_count"), "items=", len(d.get("items") or []) if "items" in d else d)

rl = gh_api("https://api.github.com/rate_limit")
try:
    print("RATE search:", rl["resources"]["search"]["remaining"], "/", rl["resources"]["search"]["limit"],
          "core:", rl["resources"]["core"]["remaining"], "/", rl["resources"]["core"]["limit"])
except Exception as e:
    print("RATE_ERR", str(rl)[:140])

# trending local probe
try:
    req = urllib.request.Request("https://github.com/trending?since=daily",
        headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req, timeout=12, context=ctx) as r2:
        h = r2.read().decode("utf-8","replace")
    print("TRENDING_LOCAL: OK bytes=%d cards=%d" % (len(h), h.count('<article class="Box-row">')))
except Exception as e:
    print("TRENDING_LOCAL: FAIL", type(e).__name__, str(e)[:80])

# token check
tok = None
for p in ("D:/hermes/data/credentials/github_token.txt","D:/hermes/data/credentials/github.token"):
    if os.path.exists(p):
        tok = open(p).read().strip(); break
print("TOKEN:", "yes" if tok else "no")
