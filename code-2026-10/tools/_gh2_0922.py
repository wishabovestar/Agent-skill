import urllib.request, ssl, re, json
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url, timeout=30):
    req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8","replace")
h=get("https://github.com/trending?since=daily")
rows=re.findall(r'<article class="Box-row">(.*?)</article>', h, re.S)
print("ROWS", len(rows))
out=[]
for r in rows:
    m=re.search(r'<h2[^>]*>\s*<a href="/([^"]+)"', r, re.S)
    d=re.search(r'<p class="col-9 color-fg-muted my-1 pr-4">\s*(.*?)\s*</p>', r, re.S)
    lang=re.search(r'itemprop="programmingLanguage">([^<]+)<', r)
    stars=re.search(r'</svg>\s*([\d,]+)\s*</a>', r)
    today=re.search(r'([\d,]+)\s*stars today', r)
    name=m.group(1) if m else "?"
    desc=re.sub(r'<[^>]+>','',d.group(1)).strip() if d else ""
    out.append((name, lang.group(1) if lang else "", stars.group(1) if stars else "?", today.group(1) if today else "?", desc[:100]))
for o in out:
    print(f"- {o[0]} | {o[1]} | ⭐{o[2]} | +{o[3]} | {o[4]}")
json.dump(out, open("_gh_trend_0922.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
