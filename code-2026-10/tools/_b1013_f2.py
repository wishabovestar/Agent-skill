# -*- coding: utf-8 -*-
import urllib.request, urllib.parse, ssl, json, re, html, time, os
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
PROXY=os.environ.get("ALL_PROXY") or "socks5h://127.0.0.1:10808"
def fetch(url, proxy=False, timeout=20, enc="utf-8"):
    req=urllib.request.Request(url, headers={"User-Agent":UA,"Accept-Language":"zh-CN,zh;q=0.9"})
    op=urllib.request.build_opener(urllib.request.ProxyHandler({"http":PROXY,"https":PROXY})) if proxy else urllib.request.build_opener()
    raw=op.open(req,timeout=timeout).read()
    try: return raw.decode(enc,"ignore")
    except Exception: return raw.decode("gbk","ignore")
def tf(u,**k):
    for a in range(2):
        try: return fetch(u,**k)
        except Exception as e:
            if a==1: return "__ERR__ "+type(e).__name__+": "+str(e)[:70]
            time.sleep(2)
def clean(s):
    s=re.sub(r"<script.*?</script>","",s or "",flags=re.S); s=re.sub(r"<style.*?</style>","",s,flags=re.S)
    s=re.sub(r"<[^>]+>"," ",s); s=html.unescape(s); return re.sub(r"\s+"," ",s).strip()

print("=== 100ppi 碳酸锂快讯 ===")
h=tf("https://www.100ppi.com/kx/detail-message-1275-13-1.html")
t=clean(h)
for m in re.finditer(r"1[0-9]月\d{1,2}日[^。|]{0,120}", t):
    print(" •", m.group(0)[:160])
    if len([1])>20: break

print("\n=== SMM h5 碳酸锂 ===")
h=tf("https://hq.smm.cn/h5/Li2CO3")
t=clean(h)
for m in re.finditer(r"(?:电池级|工业级|优质)碳酸锂[^。|]{0,60}", t):
    print(" •", m.group(0)[:120])

print("\n=== OFweek 锂电 文章列表 ===")
h=tf("https://libattery.ofweek.com/CAT-36003-8100-News.html")
if isinstance(h,str) and h.startswith("__ERR__"):
    h=tf("https://libattery.ofweek.com/")
for mm in re.findall(r'<a[^>]*href="(https?://[^"]*ofweek[^"]*)"[^>]*title="([^"]{12,70})"', h or ""):
    print(" •", clean(mm[1])[:90])
for mm in re.findall(r'title="([^"]{14,70})"', h or "")[:1]:
    pass
titles=list(dict.fromkeys(re.findall(r'<a[^>]*>([^<]{14,70})</a>', h or "")))
print("-- generic --")
for x in titles[:25]:
    x=clean(x)
    if any(w in x for w in ["锂","电池","固态","碳酸","钠","储能","硅"]):
        print("  •", x[:90])

print("\n=== 七部门 新型电池产业 政策 ===")
h=tf("https://cn.bing.com/search?q="+urllib.parse.quote("七部门 新型电池产业 政策 2026")+"&count=8&setlang=zh-CN")
for mm in re.finditer(r'<li class="b_algo".*?<h2[^>]*>(.*?)</h2>.*?<p[^>]*>(.*?)</p>', h or "", re.S):
    print(" •", clean(mm.group(1))[:100],"||",clean(mm.group(2))[:160])
