import urllib.request, urllib.parse, ssl, re, json, time, sys
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url, timeout=45, extra=None):
    h={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
    if extra: h.update(extra)
    req=urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        b=r.read()
        try: return b.decode("utf-8")
        except: return b.decode("gbk","replace")
def arxiv(q, maxr=7):
    url="https://export.arxiv.org/api/query?"+urllib.parse.urlencode({"search_query":q,"start":0,"max_results":maxr,"sortBy":"submittedDate","sortOrder":"descending"})
    for attempt in range(4):
        try:
            x=get(url)
            if "<entry" in x or "<opensearch" in x:
                break
        except Exception as e:
            x="ERR:"+repr(e)
        time.sleep(6)
    entries=re.findall(r'<entry>(.*?)</entry>', x, re.S)
    out=[]
    for e in entries:
        t=re.search(r'<title>(.*?)</title>', e, re.S)
        p=re.search(r'<published>(.*?)</published>', e, re.S)
        l=re.search(r'<id>(.*?)</id>', e, re.S)
        s=re.search(r'<summary>(.*?)</summary>', e, re.S)
        out.append(((re.sub(r'\s+',' ',t.group(1)).strip() if t else "?"),
                    (p.group(1)[:10] if p else "?"),
                    (l.group(1) if l else ""),
                    (re.sub(r'\s+',' ',s.group(1)).strip()[:240] if s else "")))
    if not out: out=[("ERR",x[:200],"","")]
    return out
queries = {
 "AI_DL": 'cat:cs.LG OR cat:cs.NE OR cat:cs.AI',
 "LLM_AGENT": 'abs:"large language model" OR abs:"LLM agent" OR abs:"transformer"',
 "DIFFUSION": 'abs:"diffusion model" OR abs:"diffusion"',
 "GNN_RL_MULTIMODAL": 'abs:"graph neural network" OR abs:"reinforcement learning" OR abs:"multimodal"',
 "VIRUS": 'cat:q-bio.PE OR abs:"influenza" OR abs:"SARS-CoV-2"',
 "LITHIUM": 'all:"lithium battery" OR all:"solid-state battery" OR all:"silicon anode" OR all:"lithium sulfur"',
}
res={}
for k,q in queries.items():
    res[k]=arxiv(q, 7)
    print("=====",k)
    for r in res[k]:
        print("-", r[1], "|", r[0][:130], "|", r[2])
    sys.stdout.flush()
    time.sleep(4)
json.dump(res, open("_arxiv2_0923.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED")
