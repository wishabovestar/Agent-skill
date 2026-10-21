# -*- coding: utf-8 -*-
"""Daily brief B: news (virus + tech/finance + lithium industry)."""
import urllib.request, urllib.parse, ssl, json, time, re, os

ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
PROXY = os.environ.get("ALL_PROXY") or "socks5h://127.0.0.1:10808"
OUT = {}

def fetch(url, timeout=25, proxy=False, headers=None, enc="utf-8"):
    h = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    if headers: h.update(headers)
    req = urllib.request.Request(url, headers=h)
    if proxy:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    else:
        op = urllib.request.build_opener()
    raw = op.open(req, timeout=timeout).read()
    try: return raw.decode(enc, "ignore")
    except Exception: return raw.decode("gbk", "ignore")

def tf(url, **kw):
    for att in range(2):
        try: return fetch(url, **kw)
        except Exception as e:
            if att == 1: return f"__ERR__ {type(e).__name__}: {str(e)[:90]}"
            time.sleep(2)

# virus (proxy)
OUT["who_don"] = tf("https://www.who.int/api/news/diseaseoutbreaknews?$orderby=PublicationDateAndTime desc&$top=12&$format=json", proxy=True)
OUT["who_rss"] = tf("https://www.who.int/feeds/entity/csr/don/en/rss.xml", proxy=True)
OUT["ecdc"] = tf("https://www.ecdc.europa.eu/en/threats-and-outbreaks", proxy=True)
OUT["cidrap"] = tf("https://www.cidrap.umn.edu/", proxy=True)
OUT["cidrap_flu"] = tf("https://www.cidrap.umn.edu/influenza", proxy=True)
# science (proxy)
OUT["nature"] = tf("https://www.nature.com/nature.rss", proxy=True)
OUT["arstech"] = tf("https://feeds.arstechnica.com/arstechnica/index", proxy=True)
# chinese direct
OUT["thepaper"] = tf("https://www.thepaper.cn/")
OUT["36kr"] = tf("https://36kr.com/")
OUT["ithome"] = tf("https://www.ithome.com/rss/")
OUT["sina_tech"] = tf("https://feed.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=30&page=1")
# lithium price
OUT["ccmn_li"] = tf("https://www.ccmn.cn/lithium/")
OUT["smm_li"] = tf("https://www.smm.cn/new-energy/")
OUT["smm"] = tf("https://www.smm.cn/")
# china cdc
OUT["cdc_covid"] = tf("https://www.chinacdc.cn/jkzt/crb/zl/szkb_11803/")

for k, v in OUT.items():
    tag = "ERR" if (isinstance(v, str) and v.startswith("__ERR__")) else "OK"
    print(f"{k}: {tag} len={len(v) if v else 0}")

with open("D:/hermes/analysis/_b1013_news_raw.json", "w", encoding="utf-8") as f:
    json.dump(OUT, f, ensure_ascii=False)
print("SAVED _b1013_news_raw.json")
