# -*- coding: utf-8 -*-
import urllib.request, urllib.parse, ssl, json, re, html, time, os
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
PROXY=os.environ.get("ALL_PROXY") or "socks5h://127.0.0.1:10808"
def fetch(url, proxy=False, timeout=20, enc="utf-8"):
    req=urllib.request.Request(url, headers={"User-Agent":UA,"Accept-Language":"zh-CN,zh;q=0.9","Referer":"https://quote.eastmoney.com/"})
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

print("=== EastMoney 碳酸锂期货 LC ===")
# GFEX lithium carbonate main contract secid: 113.lcm ; try several
for sec in ["113.lcm","113.LCM","113.lc2601","113.lc0"]:
    r=tf(f"https://push2.eastmoney.com/api/qt/stock/get?secid={sec}&fields=f43,f44,f45,f46,f57,f58,f60,f169,f170,f171")
    if isinstance(r,str) and not r.startswith("__ERR__") and '"f43"' in r:
        try:
            d=json.loads(r)["data"]
            print(f" {sec}: name={d.get('f58')} last={d.get('f43')} chg%={d.get('f170')} open={d.get('f46')} high={d.get('f44')} low={d.get('f45')}")
        except Exception as e: print(f" {sec}: parse {str(e)[:60]} raw={r[:120]}")
    else:
        print(f" {sec}: {('ERR '+r[5:70]) if isinstance(r,str) and r.startswith('__ERR__') else r[:100]}")

print("\n=== 生意社 碳酸锂 detail ===")
for url in ["https://www.100ppi.com/mprice/mlist-14-1.html","https://www.100ppi.com/sf/871.html","https://www.100ppi.com/mprice/"]:
    h=tf(url); t=clean(h)
    hits=list(dict.fromkeys(re.findall(r"碳酸锂[^。；|\s]{0,60}", t)))
    pr=list(dict.fromkeys(re.findall(r"[0-9]{4,7}(?:\.[0-9]+)?\s*元[/吨]", t)))
    print(f"-- {url[-30:]} {'ERR' if isinstance(h,str) and h.startswith('__ERR__') else 'OK'+str(len(t))}")
    if hits: print("   ", " | ".join(hits[:6])[:400])
    if pr: print("   PRICES:", pr[:10])

print("\n=== OFweek 锂电 news titles ===")
h=tf("https://libattery.ofweek.com/"); R={}
for mm in re.findall(r'<a[^>]*href="([^"]*)"[^>]*>([^<]{12,60})</a>', h or ""):
    txt=clean(mm[1])
    if any(w in txt for w in ["锂","电池","碳酸","固态","硅","钠","储能"]) and len(txt)>10:
        print(" •",txt[:80],"|",mm[0][:60])

print("\n=== 东方财富 锂电/新能源 news ===")
r=tf("https://np-listapi.eastmoney.com/comm/web/getNewsByColumns?client=web&biz=web_news_col&column=345&order=1&needInteractData=0&page_index=1&page_size=20&fields=code,showTime,title,mediaName,summary&types=1,20")
if not (isinstance(r,str) and r.startswith("__ERR__")):
    try:
        j=json.loads(r); items=j.get("data",{}).get("list",[])
        for it in items[:15]:
            print(f" [{it.get('showTime','')[:10]}] {it.get('title','')[:110]}")
    except Exception as e: print("parse err",str(e)[:80], r[:150])
else: print(r[:100])
