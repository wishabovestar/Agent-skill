# -*- coding: utf-8 -*-
import urllib.request, urllib.parse, ssl, json, re, html, time, os
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
PROXY=os.environ.get("ALL_PROXY") or "socks5h://127.0.0.1:10808"
def fetch(url, proxy=False, timeout=22, enc="utf-8"):
    req=urllib.request.Request(url, headers={"User-Agent":UA,"Accept-Language":"zh-CN,zh;q=0.9"})
    op=urllib.request.build_opener(urllib.request.ProxyHandler({"http":PROXY,"https":PROXY})) if proxy else urllib.request.build_opener()
    raw=op.open(req,timeout=timeout).read()
    try: return raw.decode(enc,"ignore")
    except Exception: return raw.decode("gbk","ignore")
def tf(u,**k):
    for a in range(2):
        try: return fetch(u,**k)
        except Exception as e:
            if a==1: return "__ERR__ "+type(e).__name__+": "+str(e)[:80]
            time.sleep(2)
def clean(s):
    s=re.sub(r"<script.*?</script>","",s or "",flags=re.S); s=re.sub(r"<style.*?</style>","",s,flags=re.S)
    s=re.sub(r"<[^>]+>"," ",s); s=html.unescape(s); return re.sub(r"\s+"," ",s).strip()
def bing(q,n=8):
    url="https://cn.bing.com/search?q="+urllib.parse.quote(q)+f"&count={n}&setlang=zh-CN"
    h=tf(url)
    if isinstance(h,str) and h.startswith("__ERR__"): return []
    out=[]
    for mm in re.finditer(r'<li class="b_algo".*?<h2[^>]*>(.*?)</h2>.*?<p[^>]*>(.*?)</p>', h, re.S):
        out.append((clean(mm.group(1)), clean(mm.group(2))[:220]))
        if len(out)>=n: break
    return out

R={}
print("=== 生意社/OFweek 碳酸锂 ===")
for name,url in [("100ppi","https://www.100ppi.com/"),("ofweek_li","https://libattery.ofweek.com/"),
                 ("mysteel","https://list.mysteel.com/article?t=1&k=%E7%A2%B3%E9%85%B8%E9%94%82"),
                 ("smm_li","https://newenergy.smm.cn/")]:
    h=tf(url); R[name]=h
    t=clean(h)
    hits=list(dict.fromkeys(re.findall(r"碳酸锂[^。；|\s]{0,50}", t)))
    print(f"--{name}-- {('ERR' if isinstance(h,str) and h.startswith('__ERR__') else 'OK')}")
    print("  ", " | ".join(hits[:10])[:600])
    # price-like numbers
    pr=list(dict.fromkeys(re.findall(r"(?:碳酸锂|电池级碳酸锂)[^。；|\s]{0,20}?([0-9]{1,2}\.[0-9]{1,4}\s*万[元吨/]+)", t)))
    if pr: print("   PRICES:", pr[:8])

print("\n=== Bing targeted ===")
BQ={
 "li_now":"碳酸锂 价格 今日 电池级 万元/吨",
 "muse":"Meta Muse Wonder 模型 发布 参数",
 "solid_state":"固态电池 量产 最新进展 2026年10月",
 "nvidia":"英伟达 台积电 芯片 抛售 半导体 2026年10月",
 "openai":"OpenAI DevDay 2026 智能体 发布",
}
BR={}
for k,q in BQ.items():
    r=bing(q); BR[k]=r; print(f"--{k}--")
    for t,de in r[:5]: print("  •",t[:100],"||",de[:150])
R["_bing"]=BR
json.dump(R, open("D:/hermes/analysis/_b1013_follow.json","w",encoding="utf-8"), ensure_ascii=False)

print("\n=== WHO pneumonia RF detail ===")
raw=json.load(open("D:/hermes/analysis/_b1013_news_raw.json",encoding="utf-8"))
try:
    j=json.loads(raw["who_don"]); vals=j.get("value",j)
    it=vals[0]
    for kk in ["Title","PublicationDateAndTime","Summary","Overview","Assessment"]:
        if it.get(kk): print(f"{kk}: {clean(str(it[kk]))[:600]}")
except Exception as e: print("err",str(e)[:100])
