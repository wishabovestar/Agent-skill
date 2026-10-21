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
print("### CIDRAP Influenza")
try:
    t=clean(get("https://www.cidrap.umn.edu/influenza"))
    print(t[300:2200])
except Exception as e: print("ERR",repr(e))
print()
print("### CIDRAP COVID-19")
try:
    t=clean(get("https://www.cidrap.umn.edu/covid-19"))
    print(t[300:2200])
except Exception as e: print("ERR",repr(e))
print()
print("### LITHIUM PRICE SEARCH")
for q in ["lithium carbonate price per ton September 2026","碳酸锂 价格 元/吨"]:
    try:
        for t,s,d in gnews(q,8): print("  *",t[:130],"|",s,"|",d)
    except Exception as e: print("ERR",repr(e))
print()
print("### ANTHROPIC NEWS")
try:
    t=clean(get("https://www.anthropic.com/news"))
    print(t[:1500])
except Exception as e: print("ERR",repr(e))
print()
print("### OPENAI NEWS")
try:
    t=clean(get("https://openai.com/news/"))
    print(t[:1500])
except Exception as e: print("ERR",repr(e))
print()
print("### SMM / CnEVPost lithium")
for u in ["https://cnevpost.com/?s=lithium+carbonate","https://www.metal.com/Lithium-Carbonate"]:
    try:
        t=clean(get(u)); print("== ",u); print(t[:1200])
    except Exception as e: print("== ",u,"ERR",repr(e))
json.dump({"ok":1}, open("_round3_0923.json","w"), ensure_ascii=False)
print("SAVED")
