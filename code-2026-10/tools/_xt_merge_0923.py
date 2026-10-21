import json, os, glob, re, datetime
BASE="D:/hermes/analysis/_xt0923"
today="2026-09-23"
raw=json.load(open(f"{BASE}/raw_0923.json",encoding="utf-8"))
supp=json.load(open(f"{BASE}/supp_0923.json",encoding="utf-8"))
det=json.load(open(f"{BASE}/details_0923.json",encoding="utf-8"))
pool=json.load(open(f"{BASE}/pool_0923.json",encoding="utf-8"))

def rel(nm,desc,topics):
    t=(nm+" "+desc+" "+" ".join(topics or [])).lower(); s=0
    kw={"agent harness":5,"harness":2,"agent skills":3,"claude code":2,"mcp":3,"multi-agent":3,
      "orchestrat":4,"agent memory":3,"memory runtime":3,"self-improv":3,"agentic":2,"skills":2,
      "wechat":3,"messaging platform":3,"code review":2,"compress":2,"tool use":2,"tool router":4,
      "rag":1,"continual learning":2,"coding agent":2,"local-first":1,"deep learning":1,"neural":1,
      "reinforcement learning":1,"inference":1,"vector search":1}
    for k,v in kw.items():
        if k in t: s+=v
    return min(10,s)

# seen set
seen=set()
for f in glob.glob("D:/hermes/data/agent_knowledge/**/*.json", recursive=True):
    fp=f.replace("\\","/")
    if "/tmp/" in fp or os.path.basename(fp).startswith("_") or "2026-09-23" in fp: continue
    try: txt=open(f,encoding="utf-8",errors="ignore").read()
    except Exception: continue
    for m in re.finditer(r'github\.com/([A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+)', txt): seen.add(m.group(1).lower())
    try: d=json.loads(txt)
    except Exception: d=None
    def walk(o):
        if isinstance(o,dict):
            for k,v in o.items():
                if k in ("full_name","repo","name") and isinstance(v,str):
                    seen.add(v.split("github.com/")[-1].strip("/").lower())
                walk(v)
        elif isinstance(o,list):
            for v in o: walk(v)
    if d is not None: walk(d)

byname={}
for qmap in (raw["search"],supp):
    for q,items in qmap.items():
        for it in items:
            k=it["full_name"]
            if k in byname:
                if q not in byname[k]["source"]: byname[k]["source"].append(q)
                byname[k]["stars"]=max(byname[k]["stars"],it["stars"])
            else:
                byname[k]={"full_name":k,"stars":it["stars"],"language":it["language"],
                  "description":it.get("description",""),"topics":it.get("topics",[]),
                  "created_at":it.get("created_at",""),"pushed_at":it.get("pushed_at",""),
                  "forks":it.get("forks",0),"url":it.get("url",""),"source":[q],"period_gain":0,"license":"N/A"}
for it in pool["trending"]:
    if it["full_name"] not in byname:
        byname[it["full_name"]]={"full_name":it["full_name"],"stars":it["stars"],"language":it["language"],
          "description":it.get("description",""),"topics":[],"created_at":"","pushed_at":"","forks":0,
          "url":"https://github.com/"+it["full_name"],"source":["trending_"+it["period"]],"period_gain":it.get("period_gain",0),"license":"N/A"}
for k,v in det.items():
    if "stars" in v and k in byname:
        byname[k].update({"stars":v["stars"],"forks":v["forks"],"language":v["language"],"description":v["desc"],
          "topics":v["topics"],"created_at":v["created"],"pushed_at":v["pushed"],"license":v["license"]})

items=list(byname.values())
for it in items:
    it["is_new"]= it["full_name"].lower() not in seen
    it["relevance"]=rel(it["full_name"],it.get("description") or "",it.get("topics") or [])
    it["score"]=round(min(100,it["relevance"]*8+min(20,it["stars"]/1500.0)),1)
items.sort(key=lambda x:(-x["relevance"],not x["is_new"],-x["stars"]))
new=[x for x in items if x["is_new"]]

# ---- algo subset ----
ALGO_Q={"dl_new","nn_new","transformer","agent_algo","algo_topic","s_dl_new","s_nn_new","s_rl_new","s_vec","s_llm_infra"}
algo_items=[it for it in items if set(it.get("source") or []) & ALGO_Q]
algo_rec={"date":today,"collected_at":datetime.datetime.now().isoformat(timespec="seconds"),
  "queries":{q:(raw["search"][q][0].get("total_count") if raw["search"].get(q) else (supp[q][0].get("total_count") if supp.get(q) else 0)) for q in ALGO_Q},
  "count":len(algo_items),"items":sorted(algo_items,key=lambda x:-x["stars"])}
json.dump(algo_rec,open("D:/hermes/data/agent_knowledge/算法/github_algo_scout_2026-09-23.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)

agent_rec={"date":today,"collected_at":datetime.datetime.now().isoformat(timespec="seconds"),
  "trending":len(pool["trending"]),"queries":len(raw["search"])+len(supp),
  "search_items":sum(len(v) for v in raw["search"].values())+sum(len(v) for v in supp.values()),
  "seen_repos":len(seen),"new_count":len(new),"count":len(items),
  "top":items[:60],"new":new}
json.dump(agent_rec,open("D:/hermes/data/agent_knowledge/ai_agent/github_scout_2026-09-23.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
json.dump({"date":today,"new":new,"top":[x for x in items if x["relevance"]>=4][:60]},
  open("D:/hermes/data/agent_knowledge/AI-agent-toolchain/github_scout_2026-09-23.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
json.dump(agent_rec,open(f"{BASE}/merged_0923.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)

lp="D:/hermes/data/agent_knowledge/_collection_log.json"
try: log=json.load(open(lp,encoding="utf-8"))
except Exception: log=[]
if isinstance(log,dict): log=log.get("entries",[])
log=[e for e in log if not (isinstance(e,dict) and e.get("date")==today and e.get("job")=="xuntian-github-scout")]
log.append({"date":today,"job":"xuntian-github-scout","trending":len(pool["trending"]),
  "queries":len(raw["search"])+len(supp),"search_items":agent_rec["search_items"],
  "seen":len(seen),"new_unique":len(new),"algo_saved":len(algo_items),"agent_saved":len(items)})
json.dump(log,open(lp,"w",encoding="utf-8"),ensure_ascii=False,indent=1)

# ---- markdown ----
top10=sorted([x for x in items if x["relevance"]>=6],key=lambda x:(-x["relevance"],not x["is_new"],-x["stars"]))[:10]
md=[f"# 巡天GitHub侦察报告 {today}","",
 f"- Trending: daily 8 / weekly 21（{len(pool['trending'])} 张卡片，本地直连成功）",
 f"- Search: {len(raw['search'])+len(supp)} 组查询 / {agent_rec['search_items']} 条结果（主13+补充10）",
 f"- 知识库已见 {len(seen)} 仓库 → 本轮候选 {len(items)}，**新入库 {len(new)}**",
 f"- 算法/DL/NN 入库 {len(algo_items)} 条 → `agent_knowledge/算法/github_algo_scout_2026-09-23.json`","",
 "## 本周高价值 Top 10","","| # | 项目 | ⭐ | 语言 | 相关性 | 新增 | 简介 |","|:--:|:--|--:|:--|:--:|:--:|:--|"]
for i,it in enumerate(top10,1):
    md.append(f"| {i} | [{it['full_name']}]({it['url']}) | {it['stars']:,} | {it['language']} | {it['relevance']}/10 | {'🆕' if it['is_new'] else '—'} | {(it['description'] or '')[:110]} |")
md+=["","## 本轮新入库项目",""]
for it in sorted(new,key=lambda x:(-x["relevance"],-x["stars"]))[:25]:
    md.append(f"- **{it['full_name']}** ⭐{it['stars']:,} {it['language']} rel={it['relevance']} ({it['created_at']}) — {(it['description'] or '')[:120]}")
md+=["","## 算法/DL/NN 采集（新入库优先级，Top 12）",""]
algo_new=sorted([x for x in algo_items if x["is_new"]],key=lambda x:x["created_at"],reverse=True)
pick=(algo_new or sorted(algo_items,key=lambda x:-x["stars"]))[:12]
for it in pick:
    md.append(f"- **{it['full_name']}** ⭐{it['stars']:,} ({it['created_at']}) — {(it['description'] or '')[:130]}")
open("D:/hermes/data/agent_knowledge/算法/xuntian_github_scout_2026-09-23.md","w",encoding="utf-8").write("\n".join(md))
open(f"{BASE}/report_0923.md","w",encoding="utf-8").write("\n".join(md))
print(f"MERGED total={len(items)} new={len(new)} algo={len(algo_items)}")
print("NEW_TOP:")
for it in sorted(new,key=lambda x:(-x["relevance"],-x["stars"]))[:12]:
    print(f"{it['full_name']}|{it['stars']}|rel{it['relevance']}|{it['language']}|{it['created_at']}|{(it['description'] or '')[:70]}")
