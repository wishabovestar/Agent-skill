import urllib.request, ssl, re, json, sys, html
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url, timeout=30):
    h={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
       "Accept-Language":"zh-CN,zh;q=0.9,en;q=0.8"}
    req=urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        b=r.read()
        for enc in ("utf-8","gbk"):
            try: return b.decode(enc)
            except: pass
        return b.decode("utf-8","replace")
def txt(h):
    h=re.sub(r'<script.*?</script>','',h,flags=re.S); h=re.sub(r'<style.*?</style>','',h,flags=re.S)
    h=re.sub(r'<[^>]+>',' ',h); h=html.unescape(h); return re.sub(r'\s+',' ',h).strip()
targets = {
 "WHO_DON": "https://www.who.int/feeds/entity/csr/don/en/rss.xml",
 "WHO_NEWS": "https://www.who.int/rss-feeds/news-english.xml",
 "ECDC": "https://www.ecdc.europa.eu/en/taxonomy/term/1665/feed",
 "CIDRAP": "https://www.cidrap.umn.edu/news-perspective",
 "GOOGLE_NEWS_VIRUS": "https://news.google.com/rss/search?q=influenza+OR+COVID+variant&hl=en-US&gl=US&ceid=US:en",
 "GOOGLE_NEWS_AI": "https://news.google.com/rss/search?q=AI+model+release&hl=en-US&gl=US&ceid=US:en",
 "GOOGLE_NEWS_LI": "https://news.google.com/rss/search?q=lithium+battery+price&hl=en-US&gl=US&ceid=US:en",
 "GOOGLE_NEWS_TECH": "https://news.google.com/rss/search?q=semiconductor+chip+earnings&hl=en-US&gl=US&ceid=US:en",
 "ITHOME": "https://www.ithome.com/rss/",
 "36KR": "https://36kr.com/feed",
 "THepaper": "https://www.thepaper.cn/",
}
res={}
for k,u in targets.items():
    try:
        h=get(u)
        items=re.findall(r'<item>(.*?)</item>', h, re.S)
        if items:
            lst=[]
            for it in items[:12]:
                t=re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', it, re.S)
                l=re.search(r'<link>(.*?)</link>', it, re.S)
                d=re.search(r'<pubDate>(.*?)</pubDate>', it, re.S)
                de=re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', it, re.S)
                lst.append({"t":html.unescape(t.group(1)).strip() if t else "",
                            "u":l.group(1).strip() if l else "",
                            "d":d.group(1).strip() if d else "",
                            "de":re.sub(r'<[^>]+>','',html.unescape(de.group(1))).strip()[:200] if de else ""})
            res[k]={"type":"rss","items":lst}
            print("===",k,"OK",len(lst))
            for i in lst[:8]:
                print("  *",i["t"][:120],"|",i["d"][:25])
        else:
            t=txt(h)
            res[k]={"type":"html","text":t[:3000]}
            print("===",k,"HTML len",len(t))
            print("  ",t[:400])
    except Exception as e:
        res[k]={"type":"err","err":repr(e)}
        print("===",k,"ERR",repr(e))
    sys.stdout.flush()
json.dump(res, open("_news_0923.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED")
