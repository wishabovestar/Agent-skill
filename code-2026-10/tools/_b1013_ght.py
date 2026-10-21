# -*- coding: utf-8 -*-
import urllib.request, ssl, json, re, html, time
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
def fetch(u,timeout=25,accept="text/html"):
    return urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":UA,"Accept":accept}),timeout=timeout).read().decode("utf-8","ignore")
def clean(s):
    s=re.sub(r"<[^>]+>"," ",s or ""); s=html.unescape(s); return re.sub(r"\s+"," ",s).strip()
h=fetch("https://github.com/trending?since=daily")
arts=re.findall(r'<article class="Box-row">(.*?)</article>', h, re.S)
rows=[]
for a in arts:
    m=re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"[^>]*>', a)
    name=m.group(1) if m else "?"
    name="/".join(x.strip() for x in name.split("/")[:2])
    d=re.search(r'<p class="col-9[^"]*">(.*?)</p>', a, re.S)
    desc=clean(d.group(1)) if d else ""
    today=re.search(r'([\d,]+)\s*stars today', clean(a))
    lang=re.search(r'itemprop="programmingLanguage">([^<]+)<', a)
    rows.append({"name":name,"today":today.group(1) if today else "?","desc":desc,"lang":lang.group(1) if lang else ""})
    print(f" • {name} | +{rows[-1]['today']} today | {rows[-1]['lang']} | {desc[:110]}")
print("\n--- verify stars via API ---")
for full in [r["name"] for r in rows[:10]]:
    try:
        j=json.loads(fetch(f"https://api.github.com/repos/{full}",timeout=15,accept="application/vnd.github+json"))
        print(f" {full}: STARS={j.get('stargazers_count')} created={j.get('created_at','')[:10]} pushed={j.get('pushed_at','')[:10]} lang={j.get('language')}")
    except Exception as e:
        print(f" {full}: ERR {str(e)[:60]}")
json.dump(rows, open("D:/hermes/analysis/_b1013_ghtrending.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED _b1013_ghtrending.json")
