# -*- coding: utf-8 -*-
import urllib.request, ssl, json, re, html
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
def fetch(u,timeout=25):
    return urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"text/html"}),timeout=timeout).read().decode("utf-8","ignore")
def clean(s):
    s=re.sub(r"<[^>]+>"," ",s or ""); s=html.unescape(s); return re.sub(r"\s+"," ",s).strip()
h=fetch("https://github.com/trending?since=daily")
# parse repo articles
arts=re.findall(r'<article class="Box-row">(.*?)</article>', h, re.S)
print("trending articles:",len(arts))
for a in arts[:25]:
    m=re.search(r'<h2[^>]*>.*?<a href="/([^"]+)"', a, re.S)
    name=m.group(1) if m else "?"
    d=re.search(r'<p class="col-9[^"]*">(.*?)</p>', a, re.S)
    desc=clean(d.group(1)) if d else ""
    st=re.search(r'(\d[\d,]*)\s*</a>\s*</span>\s*</div>\s*<span[^>]*>\s*<a[^>]*>', a)
    stars=re.search(r'stargazers">\s*([\d,]+)', a)
    today=re.search(r'([\d,]+)\s*stars today', a)
    print(f" • {name} | +{today.group(1) if today else '?'} today | ⭐{stars.group(1) if stars else '?'} | {desc[:100]}")
print("\n--- verify a few star counts via API ---")
for full in ["mattpocock/skills","Panniantong/Agent-Reach","paperclipai/paperclip","NousResearch/hermes-official-plugins","slopus/happy"]:
    try:
        j=json.loads(fetch(f"https://api.github.com/repos/{full}",timeout=15))
        print(f" {full}: ⭐{j.get('stargazers_count')} created={j.get('created_at','')[:10]} pushed={j.get('pushed_at','')[:10]}")
    except Exception as e:
        print(f" {full}: ERR {str(e)[:60]}")
