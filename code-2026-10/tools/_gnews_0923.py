import urllib.request, ssl, re, json, sys, html, os
os.environ.setdefault("ALL_PROXY","socks5://127.0.0.1:10808")
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url, timeout=35, proxy=False):
    h={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
       "Accept-Language":"en-US,en;q=0.9"}
    if proxy:
        op=urllib.request.build_opener(urllib.request.ProxyHandler({"http":"socks5://127.0.0.1:10808","https":"socks5://127.0.0.1:10808"}))
    else:
        op=urllib.request.build_opener()
    req=urllib.request.Request(url, headers=h)
    with op.open(req, timeout=timeout) as r:
        b=r.read()
        for enc in ("utf-8","gbk"):
            try: return b.decode(enc)
            except: pass
        return b.decode("utf-8","replace")
feeds = {
 "GN_VIRUS": "https://news.google.com/rss/search?q=influenza+OR+COVID+variant+OR+H5N1&hl=en-US&gl=US&ceid=US:en",
 "GN_AI": "https://news.google.com/rss/search?q=AI+model+release+OR+LLM&hl=en-US&gl=US&ceid=US:en",
 "GN_LI": "https://news.google.com/rss/search?q=lithium+battery+OR+carbonate+price&hl=en-US&gl=US&ceid=US:en",
 "GN_TECH": "https://news.google.com/rss/search?q=semiconductor+earnings+OR+chip&hl=en-US&gl=US&ceid=US:en",
}
res={}
for k,u in feeds.items():
    got=None
    for p in (True, False):
        try:
            h=get(u, proxy=p)
            items=re.findall(r'<item>(.*?)</item>', h, re.S)
            if items:
                lst=[]
                for it in items[:12]:
                    t=re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', it, re.S)
                    l=re.search(r'<link>(.*?)</link>', it, re.S)
                    d=re.search(r'<pubDate>(.*?)</pubDate>', it, re.S)
                    src=re.search(r'<source[^>]*>(.*?)</source>', it, re.S)
                    lst.append({"t":html.unescape(t.group(1)).strip() if t else "","u":l.group(1).strip() if l else "","d":d.group(1).strip() if d else "","s":html.unescape(src.group(1)).strip() if src else ""})
                got={"proxy":p,"items":lst}; break
        except Exception as e:
            got={"proxy":p,"err":repr(e)}
    res[k]=got
    print("===",k, "OK" if got and got.get("items") else got.get("err","empty"))
    if got and got.get("items"):
        for i in got["items"][:10]:
            print("  *",i["t"][:130],"|",i["s"],"|",i["d"][:25])
    sys.stdout.flush()
json.dump(res, open("_gnews_0923.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED")
