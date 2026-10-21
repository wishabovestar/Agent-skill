# -*- coding: utf-8 -*-
import urllib.request, ssl, json, re, html, time
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
PROXY="socks5h://127.0.0.1:10808"
def fetch(url, proxy=False, timeout=25):
    req=urllib.request.Request(url, headers={"User-Agent":UA,"Accept-Language":"zh-CN,zh;q=0.9"})
    op=urllib.request.build_opener(urllib.request.ProxyHandler({"http":PROXY,"https":PROXY})) if proxy else urllib.request.build_opener()
    return op.open(req, timeout=timeout).read().decode("utf-8","ignore")
def tf(u,**k):
    for a in range(2):
        try: return fetch(u,**k)
        except Exception as e:
            if a==1: return "__ERR__ "+str(e)[:80]
            time.sleep(2)
def clean(s):
    s=re.sub(r"<script.*?</script>","",s or "",flags=re.S); s=re.sub(r"<style.*?</style>","",s,flags=re.S)
    s=re.sub(r"<[^>]+>"," ",s); s=html.unescape(s); return re.sub(r"\s+"," ",s).strip()

OUT={}
# lithium detail
OUT["ccmn_li"] = tf("https://www.ccmn.cn/lithium/", timeout=25)
OUT["ccmn_news"] = tf("https://news.ccmn.cn/", timeout=25)
OUT["mysteel_li"] = tf("https://list.mysteel.com/article?t=1&k=碳酸锂", timeout=25)
OUT["smm_li_page"] = tf("https://www.smm.cn/new-energy/", timeout=25)
# china cdc
OUT["cdc_covid"] = tf("https://www.chinacdc.cn/jkzt/crb/zl/szkb_11803/", timeout=25)
OUT["cdc_flu"] = tf("https://www.chinacdc.cn/jkzt/crb/zl/lgxy/", timeout=25)
# WHO weekly epi
OUT["who_weekly"] = tf("https://www.who.int/publications/m/item/covid-19-epidemiological-update", proxy=True, timeout=25)
# CIDRAP flu + measles pages
OUT["cidrap_flu"] = tf("https://www.cidrap.umn.edu/influenza", proxy=True, timeout=25)
OUT["cidrap_covid"] = tf("https://www.cidrap.umn.edu/covid-19", proxy=True, timeout=25)

for k,v in OUT.items():
    print(k, "ERR" if (isinstance(v,str) and v.startswith("__ERR__")) else f"OK {len(v)}")
json.dump(OUT, open("D:/hermes/analysis/_b1012_li2.json","w",encoding="utf-8"), ensure_ascii=False)
# quick 锂 price extraction
for k in ["ccmn_li","ccmn_news","mysteel_li","smm_li_page"]:
    t=clean(OUT.get(k,""))
    hits=list(dict.fromkeys(re.findall(r"碳酸锂[^。；\s，]{0,45}", t)))
    print(f"--- {k} ---"); print(" | ".join(hits[:14]))
# virus extraction
for k in ["cdc_covid","cdc_flu","cidrap_flu","cidrap_covid"]:
    t=clean(OUT.get(k,""))
    print(f"=== {k} ==="); print(t[:700])
