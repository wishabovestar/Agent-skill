# -*- coding: utf-8 -*-
"""新闻源可用性批量探测"""
import ssl, sys, io, urllib.request, urllib.parse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=CTX))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
q = urllib.parse.quote("锂电")
URLS = [
    ("bing_www_rss", f"https://www.bing.com/news/search?q={q}&format=RSS"),
    ("bing_www_htm", f"https://www.bing.com/news/search?q={q}"),
    ("36kr", "https://36kr.com/feed"),
    ("ithome", "https://www.ithome.com/rss/"),
    ("ithome2", "https://api.ithome.com/rss/"),
    ("cls", "https://www.cls.cn/nodeapi/telegraphList?rn=20"),
    ("eastmoney", "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns?client=web&biz=web_news_col&column=350&order=1&needInteractData=0&page_index=1&page_size=20"),
    ("sina_roll", "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2515&k=&num=20&page=1"),
    ("weibo_hot", "https://weibo.com/ajax/side/hotSearch"),
    ("arxiv_list", "http://export.arxiv.org/rss/cs.AI"),
    ("hn", "https://hn.algolia.com/api/v1/search?tags=front_page"),
    ("who_don", "https://www.who.int/api/news/diseaseoutbreaknews"),
]
for name, url in URLS:
    try:
        with OPENER.open(urllib.request.Request(url, headers={"User-Agent": UA,
                        "Accept": "application/rss+xml,application/json,text/html,*/*"}), timeout=20) as r:
            b = r.read()
        t = b.decode("utf-8-sig", "ignore")
        print(f"{name:14s} HTTP {r.status} {r.headers.get('Content-Type','?')[:40]:40s} len={len(b):7d} "
              f"item={t.count('<item'):3d} json={t.lstrip()[:1] in '[{'}")
    except Exception as e:
        print(f"{name:14s} FAIL {type(e).__name__} {str(e)[:60]}")
