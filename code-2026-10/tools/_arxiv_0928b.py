import urllib.request, urllib.parse, ssl, re, json, sys, time
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url, timeout=50, headers=None):
    h={"User-Agent":"Mozilla/5.0"}
    if headers: h.update(headers)
    req=urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8","replace")
def arxiv(q, maxr=8):
    url="http://export.arxiv.org/api/query?"+urllib.parse.urlencode({"search_query":q,"start":0,"max_results":maxr,"sortBy":"submittedDate","sortOrder":"descending"})
    for attempt in range(4):
        try:
            x=get(url)
            break
        except Exception as e:
            print("   retry",attempt,repr(e)); time.sleep(6)
    else:
        return [("ERR","failed after retries","","")]
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
 "AI_DL": 'cat:cs.LG OR cat:cs.NE OR cat:cs.AI',
 "TRANSFORMER_DIFFUSION": 'abs:"transformer" OR abs:"diffusion model" OR abs:"large language model"',
 "LLM_AGENT": 'abs:"LLM agent" OR abs:"multi-agent" OR abs:"agentic"',
 "GNN_RL_MULTIMODAL": 'abs:"graph neural network" OR abs:"reinforcement learning" OR abs:"multimodal"',
 "LITHIUM": 'all:"lithium battery" OR all:"solid-state battery" OR all:"silicon anode" OR all:"lithium sulfur"',
 "LITHIUM_SPARSE": 'all:"solid electrolyte" OR all:"prelithiation" OR all:"lithium metal anode"',
}
res={}
for k,q in queries.items():
    time.sleep(4)
    res[k]=arxiv(q, 8)
    print("=====",k)
    for r in res[k]:
        print("-", r[1], "|", r[0][:140], "|", r[2])
    sys.stdout.flush()
json.dump(res, open("_arxiv_0928.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED")
