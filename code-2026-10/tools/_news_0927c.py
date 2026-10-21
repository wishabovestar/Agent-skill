import urllib.request, urllib.parse, ssl, re, json, sys, time
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url, timeout=60, tries=5):
    last=None
    for i in range(tries):
        try:
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (compatible; research)"})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return r.read().decode("utf-8","replace")
        except Exception as e:
            last=e; time.sleep(8*(i+1))
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
                    (s.group(1).strip().replace("\n"," ")[:320] if s else "")))
    return out
queries = {
 "AI_LG": 'cat:cs.LG',
 "AI_CL": 'cat:cs.CL',
 "AI_CV": 'cat:cs.CV',
}
for k,q in queries.items():
    try:
        r=arxiv(q,10)
        print("=====",k)
        for x in r: print("-", x[1], "|", x[0][:140], "|", x[2])
    except Exception as e:
        print("ERR", k, repr(e))
    sys.stdout.flush(); time.sleep(5)
