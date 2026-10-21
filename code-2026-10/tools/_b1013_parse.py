# -*- coding: utf-8 -*-
"""Retry failed news sources + parse everything."""
import urllib.request, ssl, json, re, html, time, os
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
PROXY=os.environ.get("ALL_PROXY") or "socks5h://127.0.0.1:10808"
def fetch(url, proxy=False, timeout=25, enc="utf-8"):
    req=urllib.request.Request(url, headers={"User-Agent":UA,"Accept-Language":"zh-CN,zh;q=0.9"})
    op=urllib.request.build_opener(urllib.request.ProxyHandler({"http":PROXY,"https":PROXY})) if proxy else urllib.request.build_opener()
    raw=op.open(req,timeout=timeout).read()
    try: return raw.decode(enc,"ignore")
    except Exception: return raw.decode("gbk","ignore")
def tf(u,**k):
    for a in range(3):
        try: return fetch(u,**k)
        except Exception as e:
            if a==2: return "__ERR__ "+type(e).__name__+": "+str(e)[:80]
            time.sleep(2)
def clean(s):
    s=re.sub(r"<script.*?</script>","",s or "",flags=re.S); s=re.sub(r"<style.*?</style>","",s,flags=re.S)
    s=re.sub(r"<[^>]+>"," ",s); s=html.unescape(s); return re.sub(r"\s+"," ",s).strip()

raw=json.load(open("D:/hermes/analysis/_b1013_news_raw.json",encoding="utf-8"))
print("=== ERR strings ===")
for k,v in raw.items():
    if isinstance(v,str) and v.startswith("__ERR__"): print(k,"->",v[:100])

# retries
print("\n=== Retries ===")
for name,url,px in [
    ("ccmn_li","https://www.ccmn.cn/lithium/",False),
    ("ccmn_x","https://www.ccmn.cn/xinwen/",False),
    ("smm_li","https://www.smm.cn/new-energy/",False),
    ("smm_price","https://www.smm.cn/price/",False),
    ("cdc_covid","https://www.chinacdc.cn/jkzt/crb/zl/szkb_11803/",False),
    ("who_don","https://www.who.int/api/news/diseaseoutbreaknews?$orderby=PublicationDateAndTime%20desc&$top=12&$format=json",True),
    ("ecdc_rss","https://www.ecdc.europa.eu/en/taxonomy/term/1666/feed",True),
]:
    r=tf(url,proxy=px)
    raw[name]=r
    print(f"{name}: {'ERR '+r[5:90] if isinstance(r,str) and r.startswith('__ERR__') else 'OK '+str(len(r))}")

json.dump(raw, open("D:/hermes/analysis/_b1013_news_raw.json","w",encoding="utf-8"), ensure_ascii=False)

print("\n=== ARXIV top per cat ===")
A=json.load(open("D:/hermes/analysis/_b1013_arxiv.json",encoding="utf-8"))["arxiv"]
for k,d in A.items():
    print(f"\n--{k}-- ({d['via']})")
    for it in d["items"][:4]:
        if "ERR" in it: print("  ERR",str(it)[:80]); continue
        print(f"  [{it['published'][:10]}] {it['title'][:130]}")
