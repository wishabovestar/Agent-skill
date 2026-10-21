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
def gnews_desc(q, n=7, hl="en-US", gl="US", ceid="US:en"):
    u="https://news.google.com/rss/search?"+urllib.parse.urlencode({"q":q,"hl":hl,"gl":gl,"ceid":ceid})
    h=get(u); items=re.findall(r'<item>(.*?)</item>', h, re.S); out=[]
    for it in items[:n]:
        t=re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', it, re.S)
        de=re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', it, re.S)
        d=re.search(r'<pubDate>(.*?)</pubDate>', it, re.S)
        s=re.search(r'<source[^>]*>(.*?)</source>', it, re.S)
        dd=re.sub(r'<[^>]+>','',html.unescape(de.group(1))).strip() if de else ""
        dd=re.sub(r'\s+',' ',dd)[:280]
        out.append(f"[{html.unescape(s.group(1)).strip() if s else ''} | {d.group(1)[:16] if d else ''}] {html.unescape(t.group(1)).strip()} :: {dd}")
    return out
for k,q in [("AI_MODELS","Anthropic Opus 5.5 OpenAI GPT-6 Sol Luna release"),
            ("GNEWS_CN_AI","人工智能 大模型 发布会"),
            ("WHO_OUTBREAK","WHO disease outbreak news 2026"),
            ("MEASLES_MPOX","measles mpox cholera outbreak 2026")]:
    print("#####",k)
    try:
        for x in gnews_desc(q,7): print("  *",x)
    except Exception as e: print("  ERR",repr(e))
    sys.stdout.flush()
# WHO DON RSS variants
print("##### WHO DON RSS")
for u in ["https://www.who.int/rss-feeds/disease-outbreak-news.xml",
          "https://www.who.int/feeds/entity/csr/don/en/rss.xml",
          "https://www.who.int/emergencies/disease-outbreak-news/rss.xml"]:
    try:
        h=get(u); items=re.findall(r'<item>(.*?)</item>', h, re.S)
        print("==",u,"items",len(items))
        for it in items[:10]:
            t=re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', it, re.S)
            d=re.search(r'<pubDate>(.*?)</pubDate>', it, re.S)
            print("   *",(html.unescape(t.group(1)).strip() if t else "")[:120],"|",d.group(1)[:22] if d else "")
        break
    except Exception as e: print("==",u,"ERR",repr(e))
print("SAVED")
