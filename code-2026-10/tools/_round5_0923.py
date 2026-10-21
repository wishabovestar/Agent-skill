import urllib.request, urllib.parse, ssl, re, json, sys, html
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
PROXY={"http":"socks5://127.0.0.1:10808","https":"socks5://127.0.0.1:10808"}
def get(url, timeout=30, proxy=True):
    h={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36","Accept-Language":"en-US,en;q=0.9"}
    op=urllib.request.build_opener(urllib.request.ProxyHandler(PROXY)) if proxy else urllib.request.build_opener()
    req=urllib.request.Request(url, headers=h)
    with op.open(req, timeout=timeout) as r:
        b=r.read()
        for enc in ("utf-8","gbk"):
            try: return b.decode(enc)
            except: pass
        return b.decode("utf-8","replace")
def gnews_desc(q, n=8):
    u="https://news.google.com/rss/search?"+urllib.parse.urlencode({"q":q,"hl":"en-US","gl":"US","ceid":"US:en"})
    h=get(u); items=re.findall(r'<item>(.*?)</item>', h, re.S); out=[]
    for it in items[:n]:
        t=re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', it, re.S)
        de=re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', it, re.S)
        d=re.search(r'<pubDate>(.*?)</pubDate>', it, re.S)
        s=re.search(r'<source[^>]*>(.*?)</source>', it, re.S)
        dd=re.sub(r'<[^>]+>','',html.unescape(de.group(1))).strip() if de else ""
        dd=re.sub(r'\s+',' ',dd)[:300]
        out.append(f"[{html.unescape(s.group(1)).strip() if s else ''} | {d.group(1)[:16] if d else ''}] {html.unescape(t.group(1)).strip()}\n      {dd}")
    return out
for k,q in [("AI_MODELS","Anthropic Opus 5.5 OpenAI GPT-6 Sol Luna release"),
            ("LI_PRICE","lithium carbonate price yuan per ton September 2026"),
            ("LI_FUT","lithium carbonate futures price China September 2026")]:
    print("#####",k)
    try:
        for x in gnews_desc(q,8): print("  *",x)
    except Exception as e: print("  ERR",repr(e))
    sys.stdout.flush()
print()
print("##### ITHOME detail (title+desc for key items)")
try:
    h=get("https://www.ithome.com/rss/", proxy=False)
    items=re.findall(r'<item>(.*?)</item>', h, re.S)
    for it in items[:30]:
        t=re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', it, re.S)
        ti=html.unescape(t.group(1)).strip() if t else ""
        if any(w in ti for w in ["GPT-6","Opus","骁龙","京东方","民企","AI","半导体","锂","电池","芯片","数据中心"]):
            de=re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', it, re.S)
            print("  *",ti[:100])
            if de: print("      ",re.sub(r'<[^>]+>','',html.unescape(de.group(1))).strip()[:220])
except Exception as e: print("  ERR",repr(e))
print("SAVED")
