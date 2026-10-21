import urllib.request, urllib.parse, ssl, re, json, time, os

ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_daily_1009_arxiv.json")

def get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8","replace")

def arxiv(q, maxr=6):
    url="https://export.arxiv.org/api/query?"+urllib.parse.urlencode(
        {"search_query":q,"start":0,"max_results":maxr,"sortBy":"submittedDate","sortOrder":"descending"})
    x=None
    for a in range(4):
        try:
            x=get(url); break
        except Exception as e:
            print("  retry",a,repr(e)); time.sleep(4)
    if x is None:
        return [("ERR","","","")]
    out=[]
    for e in re.findall(r'<entry>(.*?)</entry>', x, re.S):
        t=re.search(r'<title>(.*?)</title>', e, re.S)
        p=re.search(r'<published>(.*?)</published>', e, re.S)
        l=re.search(r'<id>(.*?)</id>', e, re.S)
        s=re.search(r'<summary>(.*?)</summary>', e, re.S)
        su = re.sub(r'\s+',' ', s.group(1)).strip() if s else ""
        out.append(((t.group(1).strip().replace("\n"," ") if t else "?"),
                    (p.group(1)[:10] if p else "?"),
                    (l.group(1) if l else ""),
                    su[:300]))
    return out

queries = {
 "AI_DL_NN": 'cat:cs.LG OR cat:cs.NE OR cat:cs.AI',
 "TRANSFORMER_DIFFUSION": 'abs:"transformer" OR abs:"diffusion model" OR abs:"large language model"',
 "GNN_RL_MULTIMODAL": 'abs:"graph neural network" OR abs:"reinforcement learning" OR abs:"multimodal"',
 "AGENT": 'abs:"LLM agent" OR abs:"multi-agent" OR abs:"agentic"',
 "LITHIUM": 'all:"lithium battery" OR all:"solid-state battery" OR all:"silicon anode" OR all:"lithium sulfur"',
 "LI_TECH": 'all:"solid electrolyte" OR all:"prelithiation" OR all:"lithium metal anode" OR all:"lithium air"',
}
res={}
for k,q in queries.items():
    res[k]=arxiv(q,6)
    print("###",k)
    for t,d,u,su in res[k]:
        print(" -",d,"|",t[:120])
        print("   ",u)
    print()
json.dump(res, open(OUT,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("saved", OUT)
