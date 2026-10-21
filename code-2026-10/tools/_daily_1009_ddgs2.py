import json, os, time
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"_daily_1009_ddgs2.json")
try:
    from ddgs import DDGS
except Exception:
    from duckduckgo_search import DDGS
PROXY="socks5://127.0.0.1:10808"
res={}
def run(kind,q,n=8):
    for a in range(2):
        try:
            with DDGS(proxy=PROXY,timeout=25) as d:
                return list(d.news(q,max_results=n) if kind=="news" else d.text(q,max_results=n))
        except Exception as e:
            print("  retry",a,repr(e)[:110]); time.sleep(3)
    return []
JOBS={
 "VAR":   [("news","COVID-19 variant dominant October 2026"),
           ("news","RSV measles outbreak October 2026"),
           ("news","CDC variant proportion BA lineage 2026")],
 "AI":    [("news","OpenAI GPT release October 2026"),
           ("news","Anthropic Claude new model October 2026"),
           ("news","Google Gemini release October 2026"),
           ("text","open source LLM agent framework 2026 release")],
 "LI":    [("news","CATL solid state battery mass production 2026"),
           ("news","lithium carbonate price October 2026 China"),
           ("text","solid state battery silicon anode paper 2026 Nature")],
 "FIN":   [("news","Apple Microsoft Alphabet earnings October 2026"),
           ("news","TSMC Q3 2026 earnings AI demand"),
           ("news","China new energy vehicle policy October 2026")],
}
for sec,jobs in JOBS.items():
    res[sec]=[]
    print("###",sec)
    for kind,q in jobs:
        r=run(kind,q)
        res[sec].append({"q":q,"kind":kind,"items":r})
        print("  >>",q,"->",len(r))
        for it in r[:6]:
            t=it.get("title") or ""; u=it.get("url") or it.get("href") or ""
            b=(it.get("body") or it.get("description") or "")[:200]; dt=it.get("date") or it.get("published") or ""
            print("    -",dt,"|",t[:110]); print("      ",u[:120])
            if b: print("      ",b.replace("\n"," "))
        time.sleep(2)
    print()
json.dump(res,open(OUT,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
print("saved",OUT)
