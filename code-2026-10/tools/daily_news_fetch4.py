"""Fetch v5 - arxiv battery retry with backoff + English virus/WHO news."""
import re, ssl, socket, time, urllib.request, urllib.parse
try:
    import socks
    socks.set_default_proxy(socks.SOCKS5,"127.0.0.1",10808); socket.socket=socks.socksocket
except Exception as e: print("socks fail",e)
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
OUT=[]
def log(s): OUT.append(str(s)); print(s)
def get(url,timeout=60):
    return urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":UA}),timeout=timeout,context=ctx).read().decode("utf-8","ignore")
def gnews(query,n=8,lang="en-US",gl="US",ceid="US:en"):
    try:
        x=get(f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl={lang}&gl={gl}&ceid={ceid}",timeout=40)
        res=[]
        for it in re.findall(r"<item>(.*?)</item>",x,re.S)[:n]:
            t=re.search(r"<title>(.*?)</title>",it,re.S); d=re.search(r"<pubDate>(.*?)</pubDate>",it,re.S); s=re.search(r"<source[^>]*>(.*?)</source>",it,re.S)
            res.append((t.group(1).strip() if t else "", s.group(1).strip() if s else "", d.group(1).strip() if d else ""))
        return res
    except Exception as e: return [("ERR "+repr(e),"","")]
def show(t,q,**kw):
    log(f"\n=== {t} :: {q} ===")
    for a,b,c in gnews(q,**kw): log(f"- {a} [{b}] {c}")

show("WHO-recent","WHO disease outbreak OR pandemic when:7d")
show("FLU-recent","H5N1 OR bird flu OR influenza variant when:7d")
show("COVID-recent","COVID variant OR SARS-CoV-2 when:7d")
show("MEASLES-recent","measles OR mpox OR ebola outbreak when:14d")

def arxiv(query,n=10):
    x=get(f"http://export.arxiv.org/api/query?search_query={query}&sortBy=submittedDate&sortOrder=descending&max_results={n}")
    titles=re.findall(r"<title>(.*?)</title>",x,re.S); ids=re.findall(r"<id>(http://arxiv.org/abs/.*?)</id>",x,re.S)
    return [(" ".join(titles[i].split()), ids[i-1] if i-1<len(ids) else "") for i in range(1,len(titles))]

queries=[
 ("battery","all:%22lithium+battery%22+OR+all:%22solid-state+battery%22+OR+all:%22silicon+anode%22+OR+all:%22lithium+sulfur%22"),
 ("battery2","all:%22lithium-ion%22+OR+all:%22electrolyte%22+OR+all:%22cathode%22+OR+all:%22sodium-ion+battery%22"),
 ("multimodal-gnn-rl","abs:%22graph+neural+network%22+OR+abs:%22reinforcement+learning%22+OR+abs:multimodal"),
]
last=None
for name,q in queries:
    for attempt in range(3):
        try:
            log(f"\n=== ARXIV {name} (attempt {attempt+1}) ===")
            r=arxiv(q)
            for i,(t,u) in enumerate(r,1): log(f"{i}. {t[:145]} | {u}")
            last=None; break
        except Exception as e:
            last=e; log(f"  fail: {repr(e)}"); time.sleep(45)
    time.sleep(35)

open(r"D:\hermes\analysis\news_fetch4.txt","w",encoding="utf-8").write("\n".join(OUT))
print("\n[SAVED]")
