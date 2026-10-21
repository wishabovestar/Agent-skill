import sys, json, os, re, html, urllib.request, urllib.parse, time, xml.etree.ElementTree as ET
PROXY="http://127.0.0.1:8899"
opener=urllib.request.build_opener(urllib.request.ProxyHandler({"http":PROXY,"https":PROXY}))

print("=== ddgs check ===")
try:
    from ddgs import DDGS
    print("ddgs package OK")
except Exception as e:
    print("ddgs import fail:", repr(e))
try:
    from duckduckgo_search import DDGS as D2
    print("duckduckgo_search OK")
except Exception as e:
    print("dds import fail:", repr(e))

def fetch(url, timeout=25):
    req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"})
    with opener.open(req, timeout=timeout) as r:
        return r.read().decode("utf-8","replace")

FEEDS = {
 "WHO_DON":"https://www.who.int/feeds/entity/csr/don/en/rss.xml",
 "CDC_FLU":"https://tools.cdc.gov/api/v2/resources/media/316422.rss",
 "CIDRAP":"https://www.cidrap.umn.edu/news/rss",
 "ITHOME":"https://www.ithome.com/rss/",
 "36KR":"https://36kr.com/feed",
 "XINHUA_TECH":"http://www.xinhuanet.com/tech/news_tech.xml",
 "SCIENCEDAILY":"https://www.sciencedaily.com/rss/top/science.xml",
}
for k,u in FEEDS.items():
    try:
        d=fetch(u)
        items=re.findall(r'<item>(.*?)</item>', d, re.S)[:4]
        print("\n###",k,"items:",len(items))
        for it in items:
            t=re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', it, re.S)
            l=re.search(r'<link>(.*?)</link>', it, re.S)
            pd=re.search(r'<pubDate>(.*?)</pubDate>', it, re.S)
            print("  -", html.unescape(t.group(1).strip())[:110] if t else "?")
            print("    ", (l.group(1).strip()[:120] if l else ""), "|", pd.group(1)[:20] if pd else "")
    except Exception as e:
        print("\n###",k,"ERR",repr(e))
