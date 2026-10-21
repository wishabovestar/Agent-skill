import json, os, time, traceback
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_daily_1009_ddgs.json")

try:
    from ddgs import DDGS
except Exception:
    from duckduckgo_search import DDGS

PROXY = "socks5://127.0.0.1:10808"
res = {}

def run(kind, q, n=8):
    for attempt in range(2):
        try:
            with DDGS(proxy=PROXY, timeout=25) as d:
                if kind == "news":
                    r = list(d.news(q, max_results=n))
                else:
                    r = list(d.text(q, max_results=n))
            return r
        except Exception as e:
            print("   retry", attempt, repr(e)[:120]); time.sleep(3)
    return []

JOBS = {
 "VIRUS": [("news","COVID-19 new variant surge October 2026"),
           ("news","H5N1 avian influenza human cases 2026"),
           ("news","influenza seasonal vaccine update 2026-2027"),
           ("news","WHO pandemic preparedness 2026")],
 "BATTERY": [("news","碳酸锂 价格 2026年10月 走势"),
             ("news","固态电池 量产 2026 车企"),
             ("news","硅碳负极 负极材料 2026 突破"),
             ("text","lithium sulfur battery prelithiation 2026 breakthrough")],
 "TECH": [("news","NVIDIA earnings AI chip October 2026"),
          ("news","semiconductor export controls 2026"),
          ("news","新能源 政策 2026年10月"),
          ("news","AI 大模型 发布 2026年10月")],
}

for sec, jobs in JOBS.items():
    res[sec] = []
    print("###", sec)
    for kind, q in jobs:
        r = run(kind, q)
        res[sec].append({"q": q, "kind": kind, "items": r})
        print("  >>", q, "->", len(r))
        for it in r[:6]:
            t = it.get("title") or ""
            u = it.get("url") or it.get("href") or ""
            b = (it.get("body") or it.get("description") or "")[:180]
            dt = it.get("date") or it.get("published") or ""
            print("    -", dt, "|", t[:110])
            print("      ", u[:120])
            if b: print("      ", b.replace("\n"," "))
        time.sleep(2)
    print()

json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("saved", OUT)
