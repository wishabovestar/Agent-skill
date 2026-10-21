# -*- coding: utf-8 -*-
import urllib.request, ssl, re, html
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
def fetch(u,timeout=20):
    return urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":UA,"Accept-Language":"zh-CN,zh;q=0.9"}),timeout=timeout).read().decode("utf-8","ignore")
def clean(s):
    s=re.sub(r"<script.*?</script>","",s or "",flags=re.S); s=re.sub(r"<style.*?</style>","",s,flags=re.S)
    s=re.sub(r"<[^>]+>"," ",s); s=html.unescape(s); return re.sub(r"\s+"," ",s).strip()
# flu weekly page -> find week40 link
h=fetch("https://ivdc.chinacdc.cn/cnic/zyzx/lgzb/")
ls=re.findall(r'href="([^"]+)"[^>]*>\s*(2026[^<]{0,30}第40周[^<]{0,30})', h)
print("week40 links:", ls[:3])
for u,t in ls[:1]:
    if u.startswith("/"): u="https://ivdc.chinacdc.cn"+u
    elif not u.startswith("http"): u="https://ivdc.chinacdc.cn/cnic/zyzx/lgzb/"+u
    try:
        r=fetch(u); tx=clean(r)
        print("=== flu week40 ===",u[:90])
        print(tx[:1200])
    except Exception as e: print("ERR",e)
# COVID Aug report
cu="https://www.chinacdc.cn/jksj/xgbdyq/202609/t20260918_1840296.html"
try:
    r=fetch(cu); tx=clean(r)
    i=tx.find("一、")
    print("=== COVID 2026-08 ===")
    print(tx[i:i+900] if i>0 else tx[:900])
except Exception as e: print("covid ERR",e)
