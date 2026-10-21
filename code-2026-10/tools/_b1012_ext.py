# -*- coding: utf-8 -*-
import urllib.request, ssl, json, re, html, time
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
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

d=json.load(open("D:/hermes/analysis/_b1012_li2.json",encoding="utf-8"))
# CIDRAP covid headlines: h2/h3
cd=d.get("cidrap_covid","")
titles=[]
for m in re.finditer(r"<(h2|h3)[^>]*>(.*?)</\1>", cd, re.S):
    t=clean(m.group(2))
    if t and 10<len(t)<160 and t not in ("Topics & Projects","Special project","Support Menu"): titles.append(t)
print("=== CIDRAP COVID ===")
for t in list(dict.fromkeys(titles))[:20]: print(" •",t)

# ccmn news
cn=d.get("ccmn_news","")
titles2=[]
for m in re.finditer(r"<a[^>]+href=\"([^\"]+)\"[^>]*>([^<]{10,90})</a>", cn):
    t=clean(m.group(2))
    if any(w in t for w in ["锂","电池","储能","镍","钴","新能"]): titles2.append((t,m.group(1)))
print("=== CCMN ===")
for t,l in list(dict.fromkeys(titles2))[:15]: print(" •",t,"|",l[:60])

# China CDC correct URLs
for u in ["https://www.chinacdc.cn/jkzt/crb/zl/szkb_11803/",
          "https://www.chinacdc.cn/jkzt/crb/zl/lgxy/",
          "https://www.chinacdc.cn/jkzt/crb/",
          "https://www.chinacdc.cn/jkzt/crb/zl/szkb_11803/index.html"]:
    r=tf(u)
    print("CDC", u.split("/")[-2], "->", "ERR" if str(r).startswith("__ERR__") else f"OK {len(r)}")
    if str(r).startswith("OK") or (not str(r).startswith("__ERR__")):
        tt=clean(r)
        mm=list(dict.fromkeys(re.findall(r"(全国新型冠状病毒感染疫情情况[^ ]{0,40}|流感监测周报[^ ]{0,30}|新型冠状病毒感染疫情[^ ]{0,30})", tt)))
        if mm: print("   hits:", mm[:8])
