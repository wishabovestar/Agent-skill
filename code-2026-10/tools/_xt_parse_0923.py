import json, re, os, glob

# ---------- parse trending HTML ----------
def parse_trending(path, period):
    html=open(path,encoding="utf-8",errors="ignore").read()
    blocks=html.split('<h2 class="h3 lh-condensed">')[1:]
    out=[]
    for b in blocks:
        m=re.search(r'href="/([^"/]+/[^"/?#]+)"', b)
        if not m: continue
        fn=m.group(1)
        # description
        dm=re.search(r'<p class="col-9[^"]*"[^>]*>\s*(.*?)\s*</p>', b, re.S)
        desc=re.sub(r"<[^>]+>","",dm.group(1)).strip() if dm else ""
        lang=re.search(r'itemprop="programmingLanguage">([^<]+)<', b)
        st=re.search(r'([\d,]+)\s+([\d,]+)\s+Built by\s+([\d,]+)\s+stars\s+(today|this week|this month)', b, re.S)
        tot=int(st.group(1).replace(",","")) if st else 0
        per=int(st.group(3).replace(",","")) if st else 0
        out.append({"full_name":fn,"stars":tot,"period_gain":per,"language":lang.group(1) if lang else "N/A",
                    "description":desc[:300],"period":period})
    return out

tr=[]
for p in ("daily","weekly"):
    items=parse_trending(f"D:/hermes/analysis/_xt0923/trending_{p}.html", p)
    print(f"PARSE trending_{p} n={len(items)}")
    tr+=items

raw=json.load(open("D:/hermes/analysis/_xt0923/raw_0923.json",encoding="utf-8"))

# ---------- build seen set from knowledge base ----------
seen=set(); files=0
for f in glob.glob("D:/hermes/data/agent_knowledge/**/*.json", recursive=True):
    fp=f.replace("\\","/")
    if "/tmp/" in fp or os.path.basename(fp).startswith("_"): continue
    files+=1
    try: txt=open(f,encoding="utf-8",errors="ignore").read()
    except Exception: continue
    try:
        d=json.loads(txt)
    except Exception:
        d=None
    def walk(o):
        if isinstance(o,dict):
            for k,v in o.items():
                if k in ("full_name","repo","name","url","html_url","repository") and isinstance(v,str):
                    m=re.match(r'^([A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+)$', v.split("github.com/")[-1].strip("/"))
                    if m and not v.endswith(".py"): seen.add(m.group(1).lower())
                walk(v)
        elif isinstance(o,list):
            for v in o: walk(v)
    if d is not None: walk(d)
    else:
        for m in re.finditer(r'github\.com/([A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+)', txt):
            seen.add(m.group(1).lower())
print(f"SEEN files={files} repos={len(seen)}")

# ---------- merge pool ----------
pool={}
for it in tr:
    fn=it["full_name"]
    if fn.lower() in seen: continue
    pool[fn.lower()]={"full_name":fn,"stars":it["stars"],"period_gain":it.get("period_gain",0),
        "language":it["language"],"description":it["description"],"source":["trending_"+it["period"]],
        "created_at":"","pushed_at":"","topics":[],"forks":0,"url":"https://github.com/"+fn}
for q,items in raw["search"].items():
    for it in items:
        fn=it["full_name"]
        k=fn.lower()
        if k in seen: continue
        if k in pool:
            pool[k]["source"].append(q)
            pool[k]["stars"]=max(pool[k]["stars"],it["stars"])
        else:
            pool[k]={"full_name":fn,"stars":it["stars"],"period_gain":0,"language":it["language"],
                "description":it["description"],"source":[q],"created_at":it["created_at"],
                "pushed_at":it["pushed_at"],"topics":it["topics"],"forks":it["forks"],"url":it["url"]}
json.dump({"pool":list(pool.values()),"trending":tr,"seen_count":len(seen)},
          open("D:/hermes/analysis/_xt0923/pool_0923.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
print(f"POOL unique_new={len(pool)} trending_total={len(tr)}")
