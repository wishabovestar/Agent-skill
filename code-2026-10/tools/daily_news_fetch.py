"""Daily news fetch v2 - global SOCKS proxy via PySocks + multi-source."""
import json, re, os, ssl, socket, sys

# --- global socks proxy ---
try:
    import socks
    socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 10808)
    socket.socket = socks.socksocket
    PROXY_OK = True
except Exception as e:
    PROXY_OK = False
    print("socks init fail:", e)

import urllib.request
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

OUT=[]
def log(s):
    OUT.append(str(s)); print(s)

def get(url, timeout=40, headers=None):
    h={"User-Agent":UA,"Accept":"*/*"}
    if headers: h.update(headers)
    req=urllib.request.Request(url, headers=h)
    return urllib.request.urlopen(req, timeout=timeout, context=ctx).read().decode("utf-8","ignore")

def arxiv(query, n=12):
    url=f"http://export.arxiv.org/api/query?search_query={query}&sortBy=submittedDate&sortOrder=descending&max_results={n}"
    x=get(url)
    titles=re.findall(r"<title>(.*?)</title>",x,re.S)
    ids=re.findall(r"<id>(http://arxiv.org/abs/.*?)</id>",x,re.S)
    out=[]
    for i in range(1,len(titles)):
        out.append((" ".join(titles[i].split()), ids[i-1] if i-1<len(ids) else ""))
    return out

log(f"PROXY_OK={PROXY_OK}")

# GitHub
log("\n=== GITHUB trending (created>2026-09-20, top stars) ===")
try:
    d=json.loads(get("https://api.github.com/search/repositories?q=created:>2026-09-20&sort=stars&order=desc&per_page=20",headers={"Accept":"application/vnd.github+json"}))
    for r in d.get("items",[])[:20]:
        log(f"{r['full_name']} | star:{r['stargazers_count']} | {r.get('language')} | {(r.get('description') or '')[:110]}")
except Exception as e: log("GH ERR "+repr(e))

# arXiv
log("\n=== ARXIV cs.LG latest ===")
try:
    for i,(t,u) in enumerate(arxiv("cat:cs.LG"),1): log(f"{i}. {t[:140]} | {u}")
except Exception as e: log("ARX1 ERR "+repr(e))

log("\n=== ARXIV cs.AI transformer/diffusion/LLM ===")
try:
    q="cat:cs.AI+AND+(abs:transformer+OR+abs:diffusion+OR+abs:%22large+language+model%22+OR+abs:multimodal)"
    for i,(t,u) in enumerate(arxiv(q),1): log(f"{i}. {t[:140]} | {u}")
except Exception as e: log("ARX2 ERR "+repr(e))

log("\n=== ARXIV battery/solid-state/silicon-anode/Li-S ===")
try:
    q="all:%22lithium+battery%22+OR+all:%22solid-state+battery%22+OR+all:%22silicon+anode%22+OR+all:%22lithium+sulfur%22+OR+all:%22lithium+metal%22"
    for i,(t,u) in enumerate(arxiv(q),1): log(f"{i}. {t[:140]} | {u}")
except Exception as e: log("ARX3 ERR "+repr(e))

log("\n=== ARXIV q-bio / virus ===")
try:
    q="all:%22SARS-CoV-2%22+OR+all:%22influenza+virus%22+OR+all:%22epidemic+model%22"
    for i,(t,u) in enumerate(arxiv(q,8),1): log(f"{i}. {t[:140]} | {u}")
except Exception as e: log("ARX4 ERR "+repr(e))

# Hacker News
log("\n=== HACKER NEWS top ===")
try:
    ids=json.loads(get("https://hacker-news.firebaseio.com/v0/topstories.json"))[:25]
    for i in ids[:20]:
        it=json.loads(get(f"https://hacker-news.firebaseio.com/v0/item/{i}.json",timeout=20))
        if it: log(f"{it.get('score')}pts | {it.get('title')} | {it.get('url','')}")
except Exception as e: log("HN ERR "+repr(e))

with open(r"D:\hermes\analysis\news_fetch_out.txt","w",encoding="utf-8") as f:
    f.write("\n".join(OUT))
print("\n[SAVED]")
