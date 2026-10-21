"""News fetch v3 - Google News RSS + WHO/ECDC + delayed arXiv."""
import json, re, os, ssl, socket, time
try:
    import socks
    socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 10808)
    socket.socket = socks.socksocket
except Exception as e:
    print("socks fail", e)
import urllib.request
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
OUT=[]
def log(s): OUT.append(str(s)); print(s)
def get(url,timeout=40):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*"})
    return urllib.request.urlopen(req,timeout=timeout,context=ctx).read().decode("utf-8","ignore")

def gnews(query, n=8, hl="zh-CN", gl="CN", ceid="CN:zh-Hans"):
    try:
        url=f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl={hl}&gl={gl}&ceid={ceid}"
        x=get(url)
        items=re.findall(r"<item>(.*?)</item>",x,re.S)[:n]
        res=[]
        for it in items:
            t=re.search(r"<title>(.*?)</title>",it,re.S)
            l=re.search(r"<link>(.*?)</link>",it,re.S)
            d=re.search(r"<pubDate>(.*?)</pubDate>",it,re.S)
            s=re.search(r"<source[^>]*>(.*?)</source>",it,re.S)
            res.append((t.group(1).strip() if t else "", s.group(1).strip() if s else "", d.group(1).strip() if d else ""))
        return res
    except Exception as e:
        return [("ERR "+repr(e),"","")]

import urllib.parse
def show(title, query):
    log(f"\n=== {title} :: {query} ===")
    for t,s,d in gnews(query):
        log(f"- {t} [{s}] {d}")

show("VIRUS-1", "新冠 变种 OR 流感 变种 传播")
show("VIRUS-2", "WHO 疫情 通报 OR 流行病 风险")
show("VIRUS-3", "influenza H5N1 OR COVID variant WHO")
show("AI-news-1", "AI 大模型 发布 突破")
show("AI-news-2", "Agent 框架 OR 开源 模型 发布")
show("BATTERY-1", "碳酸锂 价格")
show("BATTERY-2", "固态电池 OR 硅碳负极 OR 补锂 进展")
show("BATTERY-3", "锂电 行业 动态")
show("TECHFIN-1", "半导体 财报 OR 芯片")
show("TECHFIN-2", "新能源 政策")
show("TECHFIN-3", "科技 巨头 财报")

# WHO / ECDC RSS
log("\n=== WHO Disease Outbreak News RSS ===")
try:
    x=get("https://www.who.int/feeds/entity/csr/don/en/rss.xml")
    for it in re.findall(r"<item>(.*?)</item>",x,re.S)[:8]:
        t=re.search(r"<title>(.*?)</title>",it,re.S); d=re.search(r"<pubDate>(.*?)</pubDate>",it,re.S); l=re.search(r"<link>(.*?)</link>",it,re.S)
        log(f"- {t.group(1).strip() if t else ''} | {d.group(1).strip() if d else ''} | {l.group(1).strip() if l else ''}")
except Exception as e: log("WHO ERR "+repr(e))

log("\n=== ECDC news RSS ===")
try:
    x=get("https://www.ecdc.europa.eu/en/taxonomy/term/1668/feed")
    for it in re.findall(r"<item>(.*?)</item>",x,re.S)[:8]:
        t=re.search(r"<title>(.*?)</title>",it,re.S); d=re.search(r"<pubDate>(.*?)</pubDate>",it,re.S)
        log(f"- {t.group(1).strip() if t else ''} | {d.group(1).strip() if d else ''}")
except Exception as e: log("ECDC ERR "+repr(e))

# arxiv with long delays
def arxiv(query,n=10):
    url=f"http://export.arxiv.org/api/query?search_query={query}&sortBy=submittedDate&sortOrder=descending&max_results={n}"
    x=get(url,timeout=60)
    titles=re.findall(r"<title>(.*?)</title>",x,re.S)
    ids=re.findall(r"<id>(http://arxiv.org/abs/.*?)</id>",x,re.S)
    return [(" ".join(titles[i].split()), ids[i-1] if i-1<len(ids) else "") for i in range(1,len(titles))]

log("\n=== ARXIV cs.AI diff/LLM ===")
try:
    for i,(t,u) in enumerate(arxiv("cat:cs.AI+AND+(abs:transformer+OR+abs:diffusion+OR+abs:%22large+language+model%22)"),1): log(f"{i}. {t[:140]} | {u}")
except Exception as e: log("ARX2 ERR "+repr(e))
time.sleep(20)
log("\n=== ARXIV battery ===")
try:
    for i,(t,u) in enumerate(arxiv("all:%22lithium+battery%22+OR+all:%22solid-state+battery%22+OR+all:%22silicon+anode%22+OR+all:%22lithium+sulfur%22"),1): log(f"{i}. {t[:140]} | {u}")
except Exception as e: log("ARX3 ERR "+repr(e))

open(r"D:\hermes\analysis\news_fetch2.txt","w",encoding="utf-8").write("\n".join(OUT))
print("\n[SAVED]")
