import urllib.request, urllib.parse, ssl, re, json, sys, time
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url, timeout=60, tries=4):
    last=None
    for i in range(tries):
        try:
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (compatible; research)"})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return r.read().decode("utf-8","replace")
        except Exception as e:
            last=e; time.sleep(6*(i+1))
    raise last
def arxiv(q, maxr=8):
    url="https://export.arxiv.org/api/query?"+urllib.parse.urlencode({"search_query":q,"start":0,"max_results":maxr,"sortBy":"submittedDate","sortOrder":"descending"})
    x=get(url)
    entries=re.findall(r'<entry>(.*?)</entry>', x, re.S)
    out=[]
    for e in entries:
        t=re.search(r'<title>(.*?)</title>', e, re.S)
        p=re.search(r'<published>(.*?)</published>', e, re.S)
        l=re.search(r'<id>(.*?)</id>', e, re.S)
        s=re.search(r'<summary>(.*?)</summary>', e, re.S)
        out.append(((t.group(1).strip().replace("\n"," ") if t else "?"),
                    (p.group(1)[:10] if p else "?"),
                    (l.group(1) if l else ""),
                    (s.group(1).strip().replace("\n"," ")[:300] if s else "")))
    return out
queries = {
 "AI_DL": 'cat:cs.LG OR cat:cs.NE',
 "TRANSFORMER_DIFFUSION": 'abs:"diffusion" OR abs:"large language model" OR abs:"agent"',
 "LITHIUM": 'all:"lithium battery" OR all:"solid-state battery" OR all:"silicon anode"',
 "GNN_RL_MULTIMODAL": 'abs:"graph neural network" OR abs:"reinforcement learning" OR abs:"multimodal"',
}
res={}
for k,q in queries.items():
    try:
        res[k]=arxiv(q, 8)
        print("=====",k)
        for r in res[k]:
            print("-", r[1], "|", r[0][:135], "|", r[2])
    except Exception as e:
        print("ERR", k, repr(e)); res[k]=[]
    sys.stdout.flush()
    time.sleep(4)
json.dump(res, open("_arxiv_0927.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED")
