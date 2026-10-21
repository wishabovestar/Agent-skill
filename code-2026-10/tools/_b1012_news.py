# -*- coding: utf-8 -*-
"""Daily brief collector B: news (virus + tech/finance + lithium industry)."""
import urllib.request, urllib.parse, ssl, json, time, re, os

ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
PROXY = "socks5h://127.0.0.1:10808"
OUT = {}

def fetch(url, timeout=25, proxy=False, headers=None, enc="utf-8"):
    h = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    if headers: h.update(headers)
    req = urllib.request.Request(url, headers=h)
    if proxy:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    else:
        op = urllib.request.build_opener()
    r = op.open(req, timeout=timeout)
    raw = r.read()
    try:
        return raw.decode(enc, "ignore")
    except Exception:
        return raw.decode("gbk", "ignore")

def try_fetch(url, **kw):
    for att in range(2):
        try:
            return fetch(url, **kw)
        except Exception as e:
            if att == 1: return f"__ERR__ {type(e).__name__}: {str(e)[:90]}"
            time.sleep(2)

# ---- WHO disease outbreak news (proxy) ----
OUT["who_don"] = try_fetch("https://www.who.int/api/news/diseaseoutbreaknews?$orderby=PublicationDateAndTime desc&$top=12&$format=json",
                           proxy=True, timeout=25)
# WHO RSS
OUT["who_rss"] = try_fetch("https://www.who.int/feeds/entity/csr/don/en/rss.xml", proxy=True, timeout=25)
# CDC
OUT["cdc_flu"] = try_fetch("https://www.cdc.gov/fluview/index.html", proxy=True, timeout=25)
# ECDC
OUT["ecdc"] = try_fetch("https://www.ecdc.europa.eu/en/threats-and-outbreaks", proxy=True, timeout=25)
# CIDRAP
OUT["cidrap"] = try_fetch("https://www.cidrap.umn.edu/", proxy=True, timeout=25)

# ---- Science / global news (proxy) ----
OUT["nature"] = try_fetch("https://www.nature.com/nature.rss", proxy=True, timeout=25)
OUT["science"] = try_fetch("https://www.science.org/rss/news_current.xml", proxy=True, timeout=25)
OUT["arstech"] = try_fetch("https://feeds.arstechnica.com/arstechnica/index", proxy=True, timeout=25)
OUT["hn"] = try_fetch("https://hacker-news.firebaseio.com/v0/topstories.json", proxy=True, timeout=20)

# ---- Chinese news direct ----
OUT["thepaper"] = try_fetch("https://www.thepaper.cn/", timeout=25)
OUT["thepaper_api"] = try_fetch("https://api.thepaper.cn/contentapi/nodeCont/getByChannelIdV2?channelId=25950&pageSize=30", timeout=25)
OUT["36kr"] = try_fetch("https://36kr.com/", timeout=25)
OUT["ithome"] = try_fetch("https://www.ithome.com/rss/", timeout=25)
OUT["cnbeta"] = try_fetch("https://www.cnbeta.com.tw/backend.php", timeout=20)
OUT["sina_tech"] = try_fetch("https://feed.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=30&page=1", timeout=25)

# ---- Lithium price ----
OUT["smm"] = try_fetch("https://www.smm.cn/", timeout=25)
OUT["nbd"] = try_fetch("https://www.nbd.com.cn/", timeout=25)

for k, v in OUT.items():
    tag = "ERR" if (isinstance(v, str) and v.startswith("__ERR__")) else "OK"
    print(f"{k}: {tag} len={len(v) if v else 0}")

with open("D:/hermes/analysis/_b1012_news_raw.json", "w", encoding="utf-8") as f:
    json.dump(OUT, f, ensure_ascii=False)
print("SAVED _b1012_news_raw.json")
