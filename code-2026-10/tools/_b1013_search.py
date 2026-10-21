# -*- coding: utf-8 -*-
"""Search: lithium price + AI model releases + tech finance via Bing/DDGS."""
import urllib.request, urllib.parse, ssl, json, re, html, time, os
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
PROXY=os.environ.get("ALL_PROXY") or "socks5h://127.0.0.1:10808"
def fetch(url, proxy=False, timeout=20):
    req=urllib.request.Request(url, headers={"User-Agent":UA,"Accept-Language":"zh-CN,zh;q=0.9"})
    op=urllib.request.build_opener(urllib.request.ProxyHandler({"http":PROXY,"https":PROXY})) if proxy else urllib.request.build_opener()
    return op.open(req,timeout=timeout).read().decode("utf-8","ignore")
def clean(s):
    s=re.sub(r"<[^>]+>"," ",s or ""); s=html.unescape(s); return re.sub(r"\s+"," ",s).strip()
def bing(q, n=10, proxy=False):
    url="https://cn.bing.com/search?q="+urllib.parse.quote(q)+f"&count={n}&setlang=zh-CN"
    for a in range(2):
        try:
            h=fetch(url,proxy=proxy); break
        except Exception as e:
            if a==1: return []
            time.sleep(2)
    out=[]
    for mm in re.finditer(r'<li class="b_algo".*?<h2[^>]*>(.*?)</h2>.*?<p[^>]*>(.*?)</p>', h, re.S):
        out.append((clean(mm.group(1)), clean(mm.group(2))[:220]))
        if len(out)>=n: break
    if not out:
        for mm in re.finditer(r'<h2[^>]*>(.*?)</h2>', h, re.S):
            out.append((clean(mm.group(1)),""))
            if len(out)>=n: break
    return out

QS={
 "li_price":"碳酸锂 价格 今日 2026年10月",
 "li_price2":"碳酸锂 期货 现货 报价 最新",
 "li_sector":"锂电 固态电池 产业 动态 2026年10月",
 "ai_model":"OpenAI 谷歌 新模型 发布 2026年10月",
 "ai_model2":"大模型 发布 开源 2026年10月",
 "chip":"台积电 英伟达 2nm 半导体 2026年10月",
 "ev_policy":"新能源汽车 固态电池 政策 标准 2026",
 "tech_fin":"科技 巨头 财报 2026年 三季度",
}
res={}
for k,q in QS.items():
    r=bing(q); res[k]=r; print(f"--{k}--")
    for t,de in r[:6]: print("  •",t[:105],"||",de[:140])
json.dump(res, open("D:/hermes/analysis/_b1013_bing.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
