import ssl, urllib.request, time
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36","Accept":"application/json"}
def probe(name,url,to=12):
    t=time.time()
    try:
        req=urllib.request.Request(url,headers=UA)
        with urllib.request.urlopen(req,timeout=to,context=ctx) as r:
            b=r.read()
        print(f"{name}|OK|{len(b)}|{time.time()-t:.1f}s")
    except Exception as e:
        print(f"{name}|FAIL|{type(e).__name__}:{str(e)[:80]}|{time.time()-t:.1f}s")
probe("GH_API","https://api.github.com/search/repositories?q=topic:hermes-agent&sort=stars&order=desc&per_page=2")
probe("GH_TRENDING","https://github.com/trending?since=daily",10)
probe("ARXIV","http://export.arxiv.org/api/query?search_query=cat:cs.LG&max_results=2")
import socket
for p in (10808,9050):
    s=socket.socket(); s.settimeout(1.5)
    try:
        s.connect(("127.0.0.1",p)); print(f"PROXY {p}|OPEN")
    except Exception as e:
        print(f"PROXY {p}|CLOSED")
    finally:
        s.close()
