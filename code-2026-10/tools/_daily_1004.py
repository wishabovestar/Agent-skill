import urllib.request, urllib.parse, ssl, re, json, sys
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url, timeout=45, headers=None):
    h={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
       "Accept-Language":"en-US,en;q=0.9"}
    if headers: h.update(headers)
    req=urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8","replace")

def arxiv(q, maxr=8, sort="submittedDate"):
    url="http://export.arxiv.org/api/query?"+urllib.parse.urlencode({"search_query":q,"start":0,"max_results":maxr,"sortBy":sort,"sortOrder":"descending"})
    try:
        x=get(url)
    except Exception as e:
        return [("ERR", repr(e), "", "")]
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
                    (s.group(1).strip().replace("\n"," ")[:240] if s else "")))
    return out

queries = {
 "AI_DL": 'cat:cs.LG OR cat:cs.NE',
 "LLM_AGENT": 'abs:"large language model" OR abs:"LLM agent" OR abs:"agentic"',
 "TRANSFORMER_DIFFUSION": 'abs:"transformer" OR abs:"diffusion model"',
 "GNN_RL_MULTIMODAL": 'abs:"graph neural network" OR abs:"reinforcement learning" OR abs:"multimodal"',
 "LITHIUM": 'all:"lithium battery" OR all:"solid-state battery" OR all:"silicon anode" OR all:"lithium sulfur"',
 "LITHIUM2": 'all:"solid electrolyte" OR all:"prelithiation" OR all:"lithium metal anode" OR all:"Li-air"',
}
res={}
for k,q in queries.items():
    res[k]=arxiv(q, 8)
    print("=====",k)
    for r in res[k]:
        print("-", r[1], "|", r[0][:130], "|", r[2])
    sys.stdout.flush()
json.dump(res, open("_arxiv_1004.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)

# GitHub trending
trending=[]
for attempt in range(3):
    try:
        h=get("https://github.com/trending?since=daily"); break
    except Exception as e:
        print("gh retry", repr(e))
else:
    h=""
arts=re.findall(r'<article class="Box-row">(.*?)</article>', h, re.S)
print("=== TRENDING count", len(arts))
for a in arts[:25]:
    m=re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', a)
    d=re.search(r'<p class="col-9[^"]*">(.*?)</p>', a, re.S)
    s=re.search(r'stargazers</a>\s*</span>\s*([\d,]+)', a)
    st=re.search(r'(\d[\d,]*)\s*stars today', a)
    name=m.group(1) if m else "?"
    desc=re.sub(r'<[^>]+>','',d.group(1)).strip()[:120] if d else ""
    line=f"{name} | {s.group(1) if s else '?'} | +{st.group(1) if st else '?'} today | {desc}"
    print("  ", line)
    trending.append(line)
json.dump({"trending":trending}, open("_ght_1004.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED", len(trending))
