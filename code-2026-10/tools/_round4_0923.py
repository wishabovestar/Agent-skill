import urllib.request, urllib.parse, ssl, re, json, sys, html
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
PROXY={"http":"socks5://127.0.0.1:10808","https":"socks5://127.0.0.1:10808"}
def get(url, timeout=35, proxy=True):
    h={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36","Accept-Language":"en-US,en;q=0.9"}
    op=urllib.request.build_opener(urllib.request.ProxyHandler(PROXY)) if proxy else urllib.request.build_opener()
    req=urllib.request.Request(url, headers=h)
    with op.open(req, timeout=timeout) as r:
        b=r.read()
        for enc in ("utf-8","gbk"):
            try: return b.decode(enc)
            except: pass
        return b.decode("utf-8","replace")
def clean(h):
    h=re.sub(r'<script.*?</script>','',h,flags=re.S); h=re.sub(r'<style.*?</style>','',h,flags=re.S)
    h=re.sub(r'<[^>]+>',' ',h); h=html.unescape(h); return re.sub(r'\s+',' ',h).strip()
def gnews(q, n=8):
    u="https://news.google.com/rss/search?"+urllib.parse.urlencode({"q":q,"hl":"en-US","gl":"US","ceid":"US:en"})
    h=get(u); items=re.findall(r'<item>(.*?)</item>', h, re.S); out=[]
    for it in items[:n]:
        t=re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', it, re.S)
        d=re.search(r'<pubDate>(.*?)</pubDate>', it, re.S)
        s=re.search(r'<source[^>]*>(.*?)</source>', it, re.S)
        out.append([html.unescape(t.group(1)).strip() if t else "", html.unescape(s.group(1)).strip() if s else "", d.group(1)[:22] if d else ""])
    return out
print("### LI PRICE precise")
for q in ["lithium carbonate price yuan per ton this week 2026","lithium price rally September 2026 battery grade"]:
    for t,s,d in gnews(q,8): print("  *",t[:130],"|",s,"|",d)
print()
print("### WHO DON page")
try:
    print(clean(get("https://www.who.int/emergencies/disease-outbreak-news"))[:1600])
except Exception as e: print("ERR",repr(e))
print()
print("### ECDC weekly threats")
try:
    print(clean(get("https://www.ecdc.europa.eu/en/publications-data/communicable-disease-threats-report"))[:1200])
except Exception as e: print("ERR",repr(e))
print()
print("### 36kr / cnbeta tech")
for u in ["https://www.cnbeta.com.tw/backend.php","https://www.ithome.com/rss/"]:
    try:
        h=get(u, proxy=False)
        items=re.findall(r'<item>(.*?)</item>', h, re.S)
        print("==",u,"items",len(items))
        for it in items[:12]:
            t=re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', it, re.S)
            d=re.search(r'<pubDate>(.*?)</pubDate>', it, re.S)
            print("   *",(html.unescape(t.group(1)).strip() if t else "")[:110],"|",d.group(1)[:22] if d else "")
    except Exception as e: print("==",u,"ERR",repr(e))
print()
print("### GITHUB monthly")
try:
    h=get("https://github.com/trending?since=weekly")
    arts=re.findall(r'<article class="Box-row">(.*?)</article>', h, re.S)
    print("count",len(arts))
    for a in arts[:20]:
        m=re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', a)
        d=re.search(r'<p class="col-9[^"]*">(.*?)</p>', a, re.S)
        st=re.search(r'(\d[\d,]*)\s*stars today', a) or re.search(r'(\d[\d,]*)\s*stars this week', a)
        print("  ",m.group(1).strip() if m else "?","| +",st.group(1) if st else "?","|",re.sub(r'<[^>]+>','',d.group(1)).strip()[:100] if d else "")
except Exception as e: print("ERR",repr(e))
print("SAVED")
