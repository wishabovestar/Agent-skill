import json, os, datetime, re
BASE="D:/hermes/analysis/_xt0923"
raw=json.load(open(f"{BASE}/raw_0923.json",encoding="utf-8"))
det=json.load(open(f"{BASE}/details_0923.json",encoding="utf-8"))
pool=json.load(open(f"{BASE}/pool_0923.json",encoding="utf-8"))
today="2026-09-23"

def rel(nm,desc,topics):
    t=(nm+" "+desc+" "+" ".join(topics or [])).lower()
    s=0
    kw_hi={"agent harness":4,"harness":2,"agent skills":3,"claude code":2,"mcp":3,"multi-agent":3,
      "orchestrat":4,"agent memory":3,"memory runtime":3,"self-improv":3,"agentic":2,"skills":1,
      "wechat":3,"qq ":1,"messaging platform":3,"code review":2,"browser":1,"compress":2,"token":1,
      "tool use":2,"tool router":4,"rag":1,"continual learning":2,"coding agent":2,"local-first":1}
    for k,v in kw_hi.items():
        if k in t: s+=v
    return min(10,s)

# ---- build candidate list: pool + key search hits + trending ----
byname={}
for it in pool["pool"]:
    byname[it["full_name"]]=it
# add all search items not in seen (dedup by name)
for q,items in raw["search"].items():
    for it in items:
        byname.setdefault(it["full_name"],{"full_name":it["full_name"],"stars":it["stars"],
          "language":it["language"],"description":it.get("description",""),"topics":it.get("topics",[]),
          "created_at":it.get("created_at",""),"pushed_at":it.get("pushed_at",""),
          "forks":it.get("forks",0),"url":it.get("url",""),"source":[q],"period_gain":0})
for it in pool["trending"]:
    if it["full_name"] not in byname:
        byname[it["full_name"]]={"full_name":it["full_name"],"stars":it["stars"],"language":it["language"],
          "description":it.get("description",""),"topics":[],"created_at":"","pushed_at":"","forks":0,
          "url":"https://github.com/"+it["full_name"],"source":["trending_"+it["period"]],"period_gain":it.get("period_gain",0)}

for k,v in det.items():
    if "stars" in v:
        if k in byname:
            byname[k].update({"stars":v["stars"],"forks":v["forks"],"language":v["language"],
              "description":v["desc"],"topics":v["topics"],"created_at":v["created"],"pushed_at":v["pushed"],
              "license":v["license"]})
        else:
            byname[k]={"full_name":k,"stars":v["stars"],"language":v["language"],"description":v["desc"],
              "topics":v["topics"],"created_at":v["created"],"pushed_at":v["pushed"],"forks":v["forks"],
              "url":"https://github.com/"+k,"source":["trending"],"period_gain":0,"license":v["license"]}

import glob
seen=set()
for f in glob.glob("D:/hermes/data/agent_knowledge/**/*.json", recursive=True):
    fp=f.replace("\\","/")
    if "/tmp/" in fp or os.path.basename(fp).startswith("_") or "2026-09-23" in fp: continue
    try: txt=open(f,encoding="utf-8",errors="ignore").read()
    except Exception: continue
    for m in re.finditer(r'github\.com/([A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+)', txt):
        seen.add(m.group(1).lower())
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

items=list(byname.values())
newcnt=0
for it in items:
    it.setdefault("license","N/A")
    it["is_new"]= it["full_name"].lower() not in seen
    if it["is_new"]: newcnt+=1
    it["relevance"]=rel(it["full_name"],it.get("description") or "",it.get("topics") or [])
    it["score"]=round(min(100, it["relevance"]*8 + min(20, (it["stars"]/1500.0))),1)
items.sort(key=lambda x:(-x["relevance"],-x["stars"]))
print(f"NEW={newcnt} TOTAL={len(items)}")

# ---------- archive: algorithm/DL/NN ----------
ALGO_Q={"dl_new","nn_new","transformer","agent_algo","algo_topic"}
algo_items=[it for it in items if any(q in (it.get("source") or []) for q in ALGO_Q)]
algo_rec={"date":today,"collected_at":datetime.datetime.now().isoformat(timespec="seconds"),
  "queries":{q:raw["search"][q][0].get("total_count") if raw["search"].get(q) else 0 for q in ALGO_Q},
  "count":len(algo_items),
  "items":[{k:v for k,v in it.items()} for it in sorted(algo_items,key=lambda x:-x["stars"])]}
os.makedirs("D:/hermes/data/agent_knowledge/算法",exist_ok=True)
json.dump(algo_rec,open("D:/hermes/data/agent_knowledge/算法/github_algo_scout_2026-09-23.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)

# ---------- archive: agent toolchain ----------
agent_rec={"date":today,"collected_at":datetime.datetime.now().isoformat(timespec="seconds"),
  "trending_count":len(pool["trending"]),"seen_repos":pool["seen_count"],"new_pool":len(pool["pool"]),
  "count":len(items),"top":[{k:v for k,v in it.items()} for it in items[:40]]}
os.makedirs("D:/hermes/data/agent_knowledge/ai_agent",exist_ok=True)
json.dump(agent_rec,open("D:/hermes/data/agent_knowledge/ai_agent/github_scout_2026-09-23.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
json.dump({"date":today,"items":[it for it in items if it["relevance"]>=4][:60]},
  open("D:/hermes/data/agent_knowledge/AI-agent-toolchain/github_scout_2026-09-23.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)

# ---------- collection log ----------
lp="D:/hermes/data/agent_knowledge/_collection_log.json"
try: log=json.load(open(lp,encoding="utf-8"))
except Exception: log=[]
if isinstance(log,dict): log=log.get("entries",[])
log.append({"date":today,"job":"xuntian-github-scout","trending":len(pool["trending"]),
  "search_items":sum(len(v) for v in raw["search"].values()),"new_unique":len(pool["pool"]),
  "algo_saved":len(algo_items),"agent_saved":len(items)})
json.dump(log,open(lp,"w",encoding="utf-8"),ensure_ascii=False,indent=1)

# ---------- markdown report ----------
md=[f"# 巡天GitHub侦察报告 {today}","",
    f"- Trending: daily 8 / weekly 21（本周共 {len(pool['trending'])} 条热点卡片）",
    f"- Search: 13 组查询 / {sum(len(v) for v in raw['search'].values())} 条结果",
    f"- 知识库已见仓库 {pool['seen_count']} 个 → 本轮新增候选 {len(pool['pool'])} 个",
    f"- 算法/DL/NN 入库 {len(algo_items)} 条 → `agent_knowledge/算法/github_algo_scout_2026-09-23.json`","",
    "## 本周高价值 Top 10","",
    "| # | 项目 | ⭐ | 语言 | 相关性 | 新增 | 简介 |","|:--:|:--|--:|:--|:--:|:--:|:--|"]
top=sorted([x for x in items if x["relevance"]>=6],key=lambda x:(-x["relevance"],not x["is_new"],-x["stars"]))[:10]
for i,it in enumerate(top,1):
    md.append(f"| {i} | [{it['full_name']}]({it['url']}) | {it['stars']:,} | {it['language']} | {it['relevance']}/10 | {'🆕' if it['is_new'] else '—'} | {(it['description'] or '')[:110]} |")
md+=["","## 算法/DL/NN 采集（Top 12）",""]
for it in sorted(algo_items,key=lambda x:-x["stars"])[:12]:
    md.append(f"- **{it['full_name']}** ⭐{it['stars']:,} ({it['created_at']}) — {(it['description'] or '')[:130]}")
open("D:/hermes/data/agent_knowledge/算法/xuntian_github_scout_2026-09-23.md","w",encoding="utf-8").write("\n".join(md))
open(f"{BASE}/report_0923.md","w",encoding="utf-8").write("\n".join(md))

print("TOP_AGENT:")
for it in items[:12]:
    print(f"{it['full_name']}|{it['stars']}|{it['relevance']}|{it['created_at']}|{it['license']}|{(it['description'] or '')[:60]}")
print(f"ALGO_n={len(algo_items)} TOTAL_n={len(items)}")
print("FILES_OK")
