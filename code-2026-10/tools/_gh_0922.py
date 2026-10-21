import urllib.request, ssl, re, json
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url, timeout=30, headers=None):
    h={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
    if headers: h.update(headers)
    req=urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8","replace")
# try API: repos created recently, most stars
try:
    j=json.loads(get("https://api.github.com/search/repositories?q=created:%3E2026-09-08&sort=stars&order=desc&per_page=15"))
    for it in j.get("items",[]):
        print("NEW:", it["full_name"], "| ⭐", it["stargazers_count"], "|", (it.get("description") or "")[:90])
except Exception as e:
    print("API1 ERR", repr(e))
print("----- trending raw snippet -----")
try:
    h=get("https://github.com/trending?since=daily")
    print("LEN", len(h))
    idx=h.find('Box-row')
    print(repr(h[idx-200:idx+600]))
except Exception as e:
    print("TREND ERR", repr(e))
