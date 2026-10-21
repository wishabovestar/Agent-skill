import urllib.request, ssl, re, json
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url, timeout=30):
    req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8","replace")
h=get("https://github.com/trending?since=daily")
rows=re.findall(r'<article class="Box-row">(.*?)</article>', h, re.S)
seen=[]; out=[]
for r in rows:
    links=re.findall(r'href="/([\w.\-]+/[\w.\-]+)"', r)
    # repo link is the one that also has <span class="text-normal">
    name=None
    m=re.search(r'href="/([\w.\-]+/[\w.\-]+)"[^>]*>\s*<span[^>]*class="text-normal"', r)
    if m: name=m.group(1)
    if not name:
        for L in links:
            if L.count('/')==1 and not L.startswith(('login','signup','sponsors','topics','collections','orgs','settings')):
                name=L; break
    d=re.search(r'<p class="col-9 color-fg-muted my-1 pr-4">\s*(.*?)\s*</p>', r, re.S)
    lang=re.search(r'itemprop="programmingLanguage">([^<]+)<', r)
    today=re.search(r'([\d,]+)\s*stars today', r)
    stars=re.findall(r'([\d,]+)</a>', r)
    desc=re.sub(r'<[^>]+>','',d.group(1)).strip() if d else ""
    out.append({"repo":name,"lang":lang.group(1) if lang else "","stars":(stars[0] if stars else "?"),"today":(today.group(1) if today else "?"),"desc":desc[:110]})
for o in out:
    print(f"- {o['repo']} | {o['lang']} | ⭐{o['stars']} | +{o['today']} | {o['desc']}")
json.dump(out, open("_gh_trend_0922.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
# also languages trending
