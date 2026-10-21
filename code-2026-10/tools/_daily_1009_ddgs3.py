import json, os, time
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"_daily_1009_ddgs3.json")
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
            print("  retry",a,repr(e)[:100]); time.sleep(3)
    return []
JOBS={
 "LI_PRICE":[("news","battery grade lithium carbonate price per tonne October 2026"),
             ("text","碳酸锂 价格 2026年10月 电池级 元/吨")],
 "BATT_CO":[("news","CATL battery news October 2026"),
            ("news","BYD solid state battery news October 2026")],
 "AGENT":[("news","AI agent framework release October 2026"),
          ("text","GitHub trending AI agent October 2026 new open source")],
}
for sec,jobs in JOBS.items():
    res[sec]=[]
    print("###",sec)
    for kind,q in jobs:
        r=run(kind,q); res[sec].append({"q":q,"kind":kind,"items":r})
        print("  >>",q,"->",len(r))
        for it in r[:7]:
            t=it.get("title") or ""; u=it.get("url") or it.get("href") or ""
            b=(it.get("body") or it.get("description") or "")[:220]; dt=it.get("date") or it.get("published") or ""
            print("    -",dt,"|",t[:110]); print("      ",u[:120])
            if b: print("      ",b.replace("\n"," "))
        time.sleep(2)
    print()
json.dump(res,open(OUT,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
print("saved",OUT)
