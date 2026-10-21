# -*- coding: utf-8 -*-
import urllib.request, ssl, json, re, html, time, urllib.parse
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
def fetch(url, timeout=20):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent":UA,"Accept-Language":"zh-CN,zh;q=0.9"}), timeout=timeout).read().decode("utf-8","ignore")
def tf(u,**k):
    for a in range(2):
        try: return fetch(u,**k)
        except Exception as e:
            if a==1: return "__ERR__ "+str(e)[:70]
            time.sleep(2)
def clean(s):
    s=re.sub(r"<[^>]+>"," ",s or ""); s=html.unescape(s); return re.sub(r"\s+"," ",s).strip()

raw=json.load(open("D:/hermes/analysis/_b1012_news_raw.json",encoding="utf-8"))
tp=raw.get("thepaper","")
print("=== thepaper sample patterns ===")
print("NEXT_DATA:", "__NEXT_DATA__" in tp, "| newsDetail links:", len(re.findall(r"newsDetail_\d+", tp)))
# find JSON keys
for kw in ["contList","name","nodeInfo","title"]:
    print(kw, tp.count(kw))
print(tp[:0])
# try window.__INITIAL_STATE__
m=re.findall(r'"title":"([^"]{8,90})"', tp)
print("titles:", list(dict.fromkeys(m))[:30])

# Bing with cleaner queries
def bing(q, n=10):
    url="http://cn.bing.com/search?q="+urllib.parse.quote(q)+f"&count={n}"
    h=tf(url)
    if str(h).startswith("__ERR__"): return []
    out=[]
    for mm in re.finditer(r'<li class="b_algo".*?<h2[^>]*>(.*?)</h2>.*?<p[^>]*>(.*?)</p>', h, re.S):
        out.append((clean(mm.group(1)), clean(mm.group(2))[:200]))
        if len(out)>=n: break
    return out
QS={"flu":"流感 疫情通报 2026年","ev":"新能源汽车 销量 2026年10月","chip":"台积电 2nm 产能 2026","openai":"OpenAI GPT 新模型 发布 2026年10月","policy":"固态电池 政策 标准 2026"}
res={}
for k,q in QS.items():
    res[k]=bing(q); print(f"--{k}--")
    for t,de in res[k][:6]: print("  •",t[:100],"||",de[:130])
json.dump(res, open("D:/hermes/analysis/_b1012_bing2.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
