import urllib.request, urllib.parse, ssl, re, json, sys, html
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
PROXY={"http":"socks5://127.0.0.1:10808","https":"socks5://127.0.0.1:10808"}
def get(url, timeout=35, proxy=True, lang="en-US,en;q=0.9"):
    h={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36","Accept-Language":lang}
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
def gnews(q, n=10):
    u="https://news.google.com/rss/search?"+urllib.parse.urlencode({"q":q,"hl":"en-US","gl":"US","ceid":"US:en"})
    h=get(u)
    items=re.findall(r'<item>(.*?)</item>', h, re.S)
    out=[]
    for it in items[:n]:
        t=re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', it, re.S)
        d=re.search(r'<pubDate>(.*?)</pubDate>', it, re.S)
        s=re.search(r'<source[^>]*>(.*?)</source>', it, re.S)
        out.append([html.unescape(t.group(1)).strip() if t else "", html.unescape(s.group(1)).strip() if s else "", d.group(1)[:22] if d else ""])
    return out
qs = [
 ("WHO_CDC", "WHO CDC ECDC influenza COVID surveillance report"),
 ("XFG", "\"XFG\" OR \"Stratus\" OR \"Cicada\" COVID variant"),
 ("FLU", "H5N1 avian influenza human case news"),
 ("SOLID_STATE", "solid state battery silicon anode news"),
 ("LI_PRICE", "lithium carbonate price 碳酸锂 price this week"),
 ("AI_CAPEX", "AI capex data center investment billions news"),
]
res={}
for k,q in qs:
    try:
        res[k]=gnews(q, 10)
        print("===",k)
        for t,s,d in res[k]: print("  *",t[:135],"|",s,"|",d)
    except Exception as e:
        print("===",k,"ERR",repr(e))
    sys.stdout.flush()
for name,u in [("SUNSIRS_CARB","https://www.sunsirs.com/uk/prodetail-525.html"),("CHEMANALYST","https://www.chemanalyst.com/Pricing-data/lithium-carbonate-1244")]:
    try:
        t=clean(get(u))
        print("=== PRICE",name, t[:800])
    except Exception as e:
        print("=== PRICE",name,"ERR",repr(e))
    sys.stdout.flush()
try:
    h=get("https://github.com/trending?since=daily")
    arts=re.findall(r'<article class="Box-row">(.*?)</article>', h, re.S)
    print("=== TRENDING count", len(arts))
    tl=[]
    for a in arts[:25]:
        m=re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', a)
        d=re.search(r'<p class="col-9[^"]*">(.*?)</p>', a, re.S)
        st=re.search(r'(\d[\d,]*)\s*stars today', a)
        nm=m.group(1).strip() if m else "?"
        de=re.sub(r'<[^>]+>','',d.group(1)).strip()[:110] if d else ""
        tl.append(f"{nm} | +{st.group(1) if st else '?'} | {de}")
        print("  ",tl[-1])
    res["TRENDING"]=tl
except Exception as e:
    print("=== TRENDING ERR", repr(e))
json.dump(res, open("_round2_0923.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED")
