# -*- coding: utf-8 -*-
import json, re
from datetime import datetime, timezone, timedelta
d=json.load(open("D:/hermes/analysis/_b1012_arxiv.json",encoding="utf-8"))
NOW=datetime(2026,10,12,tzinfo=timezone.utc)
def parse(dt):
    try: return datetime.strptime(dt[:19],"%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except: return None
def clean(s): return re.sub(r"\s+"," ",s or "").strip()

groups={
 "AI/DL/NN 综合":["ai_dl_nn"],
 "Transformer/Attention":["transformer"],
 "Diffusion":["diffusion"],
 "GNN":["gnn"],
 "RL":["rl"],
 "多模态/VLM":["multimodal"],
 "LLM Agent":["agent_llm"],
 "锂电池":["battery_li"],
 "固态电池":["solid_state"],
 "硅负极":["silicon_anode"],
 "Li-S/Li-air":["li_s_air"],
 "预锂化":["prelithiation"],
}
out={}
for g,keys in groups.items():
    items=[]
    for k in keys:
        for it in d["arxiv"].get(k,{}).get("items",[]):
            if "ERR" in it: continue
            dt=parse(it.get("published",""))
            if dt: it["_dt"]=dt
            items.append(it)
    # dedupe by title
    seen=set(); uniq=[]
    for it in items:
        t=clean(it.get("title",""))
        if t and t.lower() not in seen:
            seen.add(t.lower()); uniq.append(it)
    # prefer recent
    uniq.sort(key=lambda x: x.get("_dt") or NOW, reverse=True)
    recent=[i for i in uniq if i.get("_dt") and (NOW-i["_dt"]).days<=8]
    pick=(recent[:6] if recent else uniq[:6])
    out[g]=[{"title":clean(i.get("title","")),"date":(i.get("_dt").strftime("%m-%d") if i.get("_dt") else ""),
             "authors":[a for a in i.get("authors",[])[:2]],"summary":clean(i.get("summary",""))[:300],
             "link":i.get("link","")} for i in pick]
    print(f"=== {g} (recent {len(recent)}) ===")
    for i in out[g]:
        print(f" [{i['date']}] {i['title'][:105]}")
json.dump(out, open("D:/hermes/analysis/_b1012_arxiv_digest.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED")
