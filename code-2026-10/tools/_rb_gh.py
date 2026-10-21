import urllib.request, urllib.parse, json, time

def gh(q, n=6):
    url = "https://api.github.com/search/repositories?q=" + urllib.parse.quote(q) + "&sort=updated&per_page=%d" % n
    req = urllib.request.Request(url, headers={"User-Agent": "redblue-exercise", "Accept": "application/vnd.github+json"})
    try:
        data = json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as e:
        return ["ERR: %s" % e]
    out = []
    for it in data.get("items", []):
        out.append("%s | %s* | %s | %s" % (it["full_name"], it.get("stargazers_count"), (it.get("pushed_at") or "")[:10], (it.get("description") or "")[:95]))
    return out

for q in ["API authorization testing BOLA", "JWT attack tool", "API security scanner OpenAPI", "authorization bypass detection"]:
    print("### " + q)
    for line in gh(q):
        print("  " + line)
    time.sleep(8)
