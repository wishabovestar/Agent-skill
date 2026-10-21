"""Fetch v4 - one-week-filtered news + battery arxiv retry."""
import re, ssl, socket, time, urllib.request, urllib.parse
try:
    import socks
    socks.set_default_proxy(socks.SOCKS5,"127.0.0.1",10808); socket.socket=socks.socksocket
except Exception as e: print("socks fail",e)
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
OUT=[]
def log(s): OUT.append(str(s)); print(s)
def get(url,timeout=45):
    return urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":UA}),timeout=timeout,context=ctx).read().decode("utf-8","ignore")
def gnews(query,n=8):
    try:
        x=get(f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans")
        res=[]
        for it in re.findall(r"<item>(.*?)</item>",x,re.S)[:n]:
            t=re.search(r"<title>(.*?)</title>",it,re.S); l=re.search(r"<link>(.*?)</link>",it,re.S)
            d=re.search(r"<pubDate>(.*?)</pubDate>",it,re.S); s=re.search(r"<source[^>]*>(.*?)</source>",it,re.S)
            res.append((t.group(1).strip() if t else "", s.group(1).strip() if s else "", d.group(1).strip() if d else ""))
        return res
    except Exception as e: return [("ERR "+repr(e),"","")]
def show(t,q):
    log(f"\n=== {t} :: {q} ===")
    for a,b,c in gnews(q): log(f"- {a} [{b}] {c}")

show("VIRUS-recent","流感 OR 新冠 疫情 when:7d")
show("VIRUS-recent2","病毒 变种 传播 when:7d")
show("VIRUS-recent3","疾控 通报 传染病 when:7d")
show("AI-recent","AI 模型 发布 when:7d")
show("AI-recent2","大模型 开源 突破 when:7d")
show("BAT-recent","碳酸锂 价格 when:7d")
show("BAT-recent2","固态电池 OR 锂电 技术 when:7d")
show("TF-recent","半导体 芯片 when:7d")
show("TF-recent2","新能源 政策 when:7d")
show("TF-recent3","科技 财报 when:14d")

def arxiv(query,n=10):
    x=get(f"http://export.arxiv.org/api/query?search_query={query}&sortBy=submittedDate&sortOrder=descending&max_results={n}",timeout=60)
    titles=re.findall(r"<title>(.*?)</title>",x,re.S); ids=re.findall(r"<id>(http://arxiv.org/abs/.*?)</id>",x,re.S)
    return [(" ".join(titles[i].split()), ids[i-1] if i-1<len(ids) else "") for i in range(1,len(titles))]
time.sleep(30)
log("\n=== ARXIV battery/solid-state/si-anode ===")
try:
    for i,(t,u) in enumerate(arxiv("all:%22lithium+battery%22+OR+all:%22solid-state+battery%22+OR+all:%22silicon+anode%22+OR+all:%22lithium+sulfur%22+OR+all:%22sodium-ion+battery%22"),1): log(f"{i}. {t[:140]} | {u}")
except Exception as e: log("ARXbat ERR "+repr(e))
time.sleep(20)
log("\n=== ARXIV GNN/RL/diffusion ===")
try:
    for i,(t,u) in enumerate(arxiv("abs:%22graph+neural+network%22+OR+abs:%22reinforcement+learning%22+OR+abs:diffusion"),1): log(f"{i}. {t[:140]} | {u}")
except Exception as e: log("ARXgnn ERR "+repr(e))

open(r"D:\hermes\analysis\news_fetch3.txt","w",encoding="utf-8").write("\n".join(OUT))
print("\n[SAVED]")
