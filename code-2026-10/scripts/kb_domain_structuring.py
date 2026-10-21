#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
kb_domain_structuring.py — 知识域结构化（MatSeek 式：结构化抽取 + 领域归并 + 可检索索引）

方法（对齐 MatSeek, ICLR2026 AI4Mat）：
  [1] STRUCTURED EXTRACTION  递归遍历源 JSON，按字段判定 repo/paper，产出一条归一化记录
  [2] DOMAIN NORMALIZATION   目录映射 + 键名主题识别 + 同义词归并 → 统一「知识领域」
  [3] DEDUP / MERGE          论文按 arXiv id（无则标题哈希）、项目按 full_name 小写去重合并
  [4] INDEXES                records.json/csv · knowledge.db(SQLite+FTS5) · INDEX.md/STATS.md · by_domain/*.md

幂等：直接覆盖输出；重复运行结果稳定。零 LLM 调用（纯启发式）。
用法： python kb_domain_structuring.py [--root D:/hermes/data/agent_knowledge] [--out .../_structured]
"""
import os, sys, re, csv, json, time, sqlite3, hashlib, glob

def arg(name, default):
    a = sys.argv
    return a[a.index(name)+1] if name in a else default

ROOT = arg("--root", r"D:\hermes\data\agent_knowledge")
OUT  = arg("--out",  os.path.join(ROOT, "_structured"))
os.makedirs(os.path.join(OUT, "by_domain"), exist_ok=True)

# ---------------------------------------------------------------- taxonomy
ARXCAT = re.compile(r'^(cs|math|stat|physics|eess|nlin|q-bio|quant-ph|astro-ph|cond-mat|q-fin|econ)\.[A-Za-z\-]+$')
EXACT = {"papers","paper","queries","query","topics","topic","main","all","new","top","trends","trend","entries","by_cat",
 "by_kw","items","repos","repo","projects","repositories","result","results","details","stats","summary","data",
 "github_repos","arxiv_papers","new_all","all_new","seen","pool","candidates","ranked","key_repos","top_results",
 "ranked_pool","misc","other","tmp","files","seen_files","seen_repos","seen_papers","row","rows","section","list","groups"}
SUBARTIF = ("all:","created","stars","kw_","_new","new_","_recent","recent_","_seg","fallback","_2026","_2025","_topic",
 "_github","highlight","仓库","incremental_","trending","weekly","scored","eligible","absorbed","honorable","topic_",
 "searchlog","_repos","repo_","_cat","_kw","_query","pool_","_top","top_","daily_","_daily","_rows","rows_")
CANON = {
 "算法原理":"算法原理","algorithms":"算法原理","algorithm":"算法原理","algorithms_github":"算法原理",
 "数学原理":"数学原理","math":"数学原理","numerical-methods":"数学原理","mathematical_optimization":"数学原理","变分法":"数学原理",
 "math_principles":"数学原理","computational_mathematics":"数学原理","linalg":"数学原理","优化理论":"算法与优化",
 "计算机原理":"计算机原理","system":"计算机原理","computer_principles":"计算机原理","计算机":"计算机原理","cs_lg":"计算机原理","csds":"算法与优化",
 "深度学习":"深度学习","dl":"深度学习","deep_learning":"深度学习","algo_deeplearning":"深度学习","神经网络训练":"深度学习","神经网络优化":"深度学习",
 "训练方法":"深度学习","大模型训练方法":"深度学习","神经网络训练框架":"深度学习","dl_deep_learning":"深度学习","深度学习框架/教程":"深度学习",
 "机器学习":"机器学习","ml":"机器学习","ml_new":"机器学习","machine_learning":"机器学习","random_forest":"机器学习","随机森林":"机器学习",
 "神经算法cnn_llm":"神经算法(CNN/LLM)","neural_cnn_llm":"神经算法(CNN/LLM)","neural":"神经算法(CNN/LLM)","cnn":"神经算法(CNN/LLM)",
 "cnn_convolutional":"神经算法(CNN/LLM)","transformer":"神经算法(CNN/LLM)","transformer变体":"神经算法(CNN/LLM)","transformer实现":"神经算法(CNN/LLM)",
 "transformer/ssm":"神经算法(CNN/LLM)","大语言模型":"神经算法(CNN/LLM)","llm":"神经算法(CNN/LLM)","混合专家":"神经算法(CNN/LLM)",
 "混合专家moe":"神经算法(CNN/LLM)","状态空间模型":"神经算法(CNN/LLM)","状态空间模型ssm":"神经算法(CNN/LLM)","dl_ssm_mamba":"神经算法(CNN/LLM)",
 "dl_moe":"神经算法(CNN/LLM)","注意力机制":"神经算法(CNN/LLM)","稀疏注意力":"神经算法(CNN/LLM)","线性注意力":"神经算法(CNN/LLM)",
 "扩散模型":"神经算法(CNN/LLM)","dl_扩散模型":"神经算法(CNN/LLM)","扩散/生成":"神经算法(CNN/LLM)","知识蒸馏压缩":"神经算法(CNN/LLM)",
 "模型蒸馏/压缩":"神经算法(CNN/LLM)","高效训练/蒸馏":"神经算法(CNN/LLM)","测试时计算":"神经算法(CNN/LLM)","神经架构搜索":"神经算法(CNN/LLM)",
 "新架构":"神经算法(CNN/LLM)","新架构(moe)":"神经算法(CNN/LLM)","高效新架构":"神经算法(CNN/LLM)","llm训练方法":"神经算法(CNN/LLM)",
 "dl_llm_训练":"神经算法(CNN/LLM)","nn_arch":"神经算法(CNN/LLM)","neural_network":"神经算法(CNN/LLM)","spec_decoding":"神经算法(CNN/LLM)",
 "quantization":"神经算法(CNN/LLM)","kv_cache":"神经算法(CNN/LLM)","moe":"神经算法(CNN/LLM)","token_compress":"神经算法(CNN/LLM)",
 "test_time":"神经算法(CNN/LLM)","sparse_attn":"神经算法(CNN/LLM)","lora":"神经算法(CNN/LLM)","diffusion_model":"神经算法(CNN/LLM)",
 "context compression":"神经算法(CNN/LLM)",
 "退火算法":"算法与优化","退火遗传":"算法与优化","simulated_annealing":"算法与优化","annealing":"算法与优化","遗传算法":"算法与优化","genetic":"算法与优化",
 "genetic_algorithm":"算法与优化","genetic-algorithm":"算法与优化","粒子群":"算法与优化","particle_swarm":"算法与优化","蚁群算法":"算法与优化","禁忌搜索":"算法与优化",
 "tabu":"算法与优化","tabu_search":"算法与优化","群体智能":"算法与优化","swarm_intel":"算法与优化","swarm_intelligence":"算法与优化","进化算法":"算法与优化",
 "进化计算(cs.ne)":"算法与优化","差分进化":"算法与优化","灰狼优化":"算法与优化","元启发式":"算法与优化","超启发式":"算法与优化","贝叶斯优化":"算法与优化",
 "束搜索":"算法与优化","贪心算法":"算法与优化","动态规划":"算法与优化","dijkstra":"算法与优化","dijkstra最短路径":"算法与优化","dijkstra_shortest_path":"算法与优化",
 "shortest_path":"算法与优化","最短路(cs.ds)":"算法与优化","供应链优化":"算法与优化","supply_chain_optimization":"算法与优化","optimization":"算法与优化",
 "pytorch":"算法与优化","算法/路径":"算法与优化","进化/群体智能":"算法与优化","incremental_assignment_hungarian":"算法与优化","algo_extension":"算法与优化",
 "算法":"算法(通用)",
 "知识图谱":"图与知识图谱","知识图谱推理":"图与知识图谱","knowledge_graph":"图与知识图谱","graph_neural_network":"图与知识图谱",
 "图神经网络":"图与知识图谱","图/知识图谱":"图与知识图谱",
 "强化学习":"强化学习","深度强化学习":"强化学习","reinforcement_learning":"强化学习","reinforcement-learning":"强化学习","rl":"强化学习","rl_reinforcement":"强化学习",
 "ai-agent工具链":"AI-Agent工具链","agent":"AI-Agent工具链","agent_fw":"AI-Agent工具链","mcp_server":"AI-Agent工具链","ai_agent_tool":"AI-Agent工具链",
 "code_assistant":"AI-Agent工具链","cli_tool":"AI-Agent工具链","search_engine":"AI-Agent工具链","agentic-ai":"AI-Agent工具链","agent_memory":"AI-Agent工具链",
 "锂电":"锂电","3d图纸/cad":"3D图纸/CAD","安全":"安全","软件开发":"软件开发","调度":"调度","仿真":"仿真",
}
CANONICAL = {"算法原理","算法与优化","算法(通用)","数学原理","计算机原理","深度学习","机器学习","神经算法(CNN/LLM)","强化学习",
 "图与知识图谱","AI-Agent工具链","开源项目侦察(GitHub)","锂电","3D图纸/CAD","安全","软件开发","调度","仿真","数学","AI模型泄露/情报","其他/未分类"}
DIRDOM = {"algorithm/算法原理":"算法原理","algorithm/机器学习":"机器学习","algorithm/深度学习":"深度学习","algorithm/神经算法CNN_LLM":"神经算法(CNN/LLM)",
 "algorithm/数学原理":"数学原理","algorithm/计算机原理":"计算机原理","algorithm/热点项目":"开源项目侦察(GitHub)","algorithm/tmp":"算法(临时采集)",
 "algorithm":"算法(通用)","算法/tmp":"算法(临时采集)","算法":"算法(通用)","github_scout":"开源项目侦察(GitHub)","ai_agent":"AI-Agent工具链",
 "AI-agent-toolchain":"AI-Agent工具链","AI_DL_research":"深度学习","ai_ml":"机器学习","AI模型泄露":"AI模型泄露/情报","3D图纸":"3D图纸/CAD",
 "CAD-PDF":"3D图纸/CAD","lithium-battery":"锂电","security":"安全","software-dev":"软件开发","调度":"调度","仿真":"仿真","数学":"数学","tmp":"算法(临时采集)"}
GEN = {"算法(通用)","算法(临时采集)","未分类"}

def clean_topic(k):
    if not isinstance(k, str): return None
    k2 = re.sub(r'^\d+_', '', k.strip()); k2 = re.sub(r'^arXiv:', '', k2, flags=re.I).strip()
    if not k2 or len(k2) > 40: return None
    if k2.lower() in CANON: return k2
    if k2.startswith("算法_"):
        k2 = k2[3:]
        if k2.lower() in CANON: return k2
    if k2 in EXACT or k2.lower() in EXACT: return None
    if ARXCAT.match(k2) or re.fullmatch(r'[0-9\.\-_: ]+', k2): return None
    if any(s in k2.lower() for s in SUBARTIF): return None
    return k2
def canon(t): return CANON.get(t.lower(), CANON.get(t, t)) if t else None
def load(p):
    for e in ("utf-8","utf-8-sig","gbk"):
        try: return json.load(open(p, encoding=e))
        except Exception: pass
    return None
def is_repo(d):
    return isinstance(d, dict) and ((isinstance(d.get("full_name"), str) and "/" in d["full_name"]) or ("stars" in d and ("name" in d or "repo" in d)))
def is_paper(d):
    return (isinstance(d, dict) and isinstance(d.get("title"), str) and len(d["title"]) >= 8
            and any(k in d for k in ("authors","abstract","summary","cats","categories","published"))
            and any(k in d for k in ("id","arxiv_id","url")))
def walk(obj, topic=None):
    if isinstance(obj, dict):
        if is_repo(obj): yield ("project", obj, topic); return
        if is_paper(obj): yield ("paper", obj, topic); return
        for k, v in obj.items():
            t = topic
            if k in ("direction","domain","category","group") and isinstance(v, str): t = clean_topic(v) or topic
            elif clean_topic(k): t = clean_topic(k)
            if isinstance(v, dict) and re.match(r'^[\w.\-]+/[\w.\-]+$', str(k)):
                vv = dict(v); vv.setdefault("full_name", k)
                if is_repo(vv): yield ("project", vv, topic); continue
            yield from walk(v, t)
    elif isinstance(obj, list):
        for v in obj: yield from walk(v, topic)
def g(d, *ks):
    for k in ks:
        if d.get(k): return d[k]
def cut(v, n=10): return str(v)[:n] if v else None
def strs(x):
    o = []
    if isinstance(x, list):
        for a in x:
            o.append(a if isinstance(a, str) else (str(g(a,"name","title","id") or "") if isinstance(a, dict) else str(a)))
    return [s for s in o if s]
def uniq(seq):
    seen = set(); o = []
    for x in seq:
        k = x if isinstance(x,(str,int,float,bool,type(None))) else json.dumps(x, ensure_ascii=False, sort_keys=True)
        if k not in seen: seen.add(k); o.append(x)
    return o

def norm(kind, d, dir_dom, topic, rd, fn, scan):
    if dir_dom in GEN:
        dom = canon(topic) if topic else ("算法(通用)" if kind == "paper" else "开源项目侦察(GitHub)")
    else:
        dom = dir_dom
    if dom not in CANONICAL: dom = "其他/未分类"
    sub = topic if (topic and canon(topic) != dom and topic != dom and len(topic) <= 30) else None
    if kind == "project":
        name = str(g(d,"full_name","repo","name") or "").strip()
        return {"kind":"project","id":name.lower(),"name":name,
                "url":g(d,"html_url","url") or (f"https://github.com/{name}" if "/" in name else None),
                "stars":d.get("stars") if isinstance(d.get("stars"),(int,float)) else None,
                "forks":d.get("forks") if isinstance(d.get("forks"),(int,float)) else None,
                "language":g(d,"language","lang"),"description":g(d,"description","desc"),"topics":strs(d.get("topics")),
                "created":cut(g(d,"created_at","created")),"pushed":cut(g(d,"pushed_at","updated_at")),"license":d.get("license"),
                "domain":dom,"subdomain":sub,"scan_date":scan,"source":f"{rd}/{fn}"}
    aid = str(g(d,"id","arxiv_id") or "").strip(); title = " ".join(str(d.get("title")).split())
    key = aid.lower() if aid else "t:" + hashlib.md5(title.lower().encode()).hexdigest()[:14]
    dt = cut(g(d,"published","date"))
    if dt and not (re.match(r'^(19|20)\d{2}-\d{2}', dt) and "2000" <= dt[:4] <= "2027"): dt = None
    return {"kind":"paper","id":key,"arxiv_id":aid or None,"title":title,
            "url":g(d,"url") or (f"https://arxiv.org/abs/{aid}" if aid else None),
            "authors":strs(d.get("authors")),"date":dt,"cats":strs(g(d,"cats","categories")),
            "summary":" ".join(str(g(d,"abstract","summary") or "").split())[:1500],
            "domain":dom,"subdomain":sub,"scan_date":scan,"source":f"{rd}/{fn}"}

def build():
    raw = []; nf = 0; nbad = 0; nskip = 0
    for dp, dns, fns in os.walk(ROOT):
        rd = os.path.relpath(dp, ROOT).replace("\\","/")
        if rd.startswith(".") or rd.startswith("_structured"): continue
        top = rd.split("/")[0]
        dir_dom = DIRDOM.get(rd) or DIRDOM.get(top, top or "未分类")
        for f in fns:
            if not f.lower().endswith(".json"): continue
            # 跳过 GitHub scout 抓回的仓库清单（npm package.json 等），它们不是知识记录
            if f.lower() == "package.json" or f.lower().endswith("__package.json"):
                if "/raw/" in ("/" + rd + "/"):
                    nskip += 1
                    continue
            p = os.path.join(dp, f)
            try:
                if os.path.getsize(p) > 20_000_000: continue
            except OSError: continue
            nf += 1; obj = load(p)
            if obj is None: nbad += 1; continue
            m = re.search(r'(20\d{2})[-_]?(\d{2})[-_]?(\d{2})', f) or re.search(r'(20\d{2})[-_]?(\d{2})[-_]?(\d{2})', rd)
            scan = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
            for kind, d, tp in walk(obj):
                try: raw.append(norm(kind, d, dir_dom, tp, rd, f, scan))
                except Exception: pass
    merged = {}
    for r in raw:
        k = (r["kind"], r["id"])
        if k not in merged: r["sources"] = [r.pop("source")]; merged[k] = r; continue
        e = merged[k]
        for f, v in r.items():
            if f in ("kind","id","sources"): continue
            if f == "stars":
                xs = [x for x in (e.get("stars"), v) if isinstance(x,(int,float))]; e["stars"] = max(xs) if xs else None
            elif f in ("topics","cats","authors") and isinstance(v, list): e[f] = uniq((e.get(f) or []) + v)
            elif f == "summary" and isinstance(v, str) and len(v) > len(e.get("summary") or ""): e["summary"] = v
            elif v not in (None,"",[],{}) and e.get(f) in (None,"",[],{}): e[f] = v
        if r.get("source") and r["source"] not in e["sources"]: e["sources"].append(r["source"])
    recs = list(merged.values())
    for r in recs: r["scans"] = len(r["sources"])
    return recs, nf, nbad, len(raw), nskip

def san(s): return re.sub(r'[\\/:*?"<>|()]', '_', s)
COLS = ["kind","id","domain","subdomain","name","url","stars","date","authors","cats","language","created","scan_date","scans","summary"]
def row(r):
    return {"kind":r["kind"],"id":r["id"],"domain":r["domain"],"subdomain":r.get("subdomain") or "","name":r.get("name") or r.get("title") or "",
            "url":r.get("url") or "","stars":r.get("stars") if r.get("stars") is not None else "","date":r.get("date") or "",
            "authors":"; ".join(r.get("authors") or []),"cats":"; ".join(r.get("cats") or []),"language":r.get("language") or "",
            "created":r.get("created") or "","scan_date":r.get("scan_date") or "","scans":r.get("scans",1),
            "summary":(r.get("summary") or "").replace("\n"," ")[:500]}

def write_out(recs, nf, nbad, nraw, nskip=0):
    import datetime
    papers = [r for r in recs if r["kind"] == "paper"]; projs = [r for r in recs if r["kind"] == "project"]
    def tot(d, k): return sum(1 for r in recs if r["domain"] == d and r["kind"] == k)
    order = sorted({r["domain"] for r in recs}, key=lambda d: -(tot(d,"paper") + tot(d,"project")))
    rows = [row(r) for r in recs]
    json.dump(recs, open(os.path.join(OUT,"records.json"),"w",encoding="utf-8"), ensure_ascii=False)
    for fn, data in (("records.csv",recs),("papers.csv",papers),("projects.csv",projs)):
        with open(os.path.join(OUT,fn),"w",newline="",encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=COLS); w.writeheader()
            for r in data: w.writerow(row(r))
    db = os.path.join(OUT,"knowledge.db")
    for x in (db, db+"-wal", db+"-shm"):
        try: os.remove(x)
        except OSError: pass
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE records(kind TEXT,id TEXT,domain TEXT,subdomain TEXT,name TEXT,url TEXT,stars REAL,date TEXT,
                 authors TEXT,cats TEXT,language TEXT,created TEXT,scan_date TEXT,scans INT,summary TEXT)""")
    con.executemany("INSERT INTO records VALUES(%s)" % ",".join("?"*len(COLS)), [tuple(rw[c] for c in COLS) for rw in rows])
    con.execute("CREATE INDEX ix_dom ON records(domain,kind)"); con.execute("CREATE INDEX ix_stars ON records(stars DESC)")
    tok = "trigram"
    try: con.execute(f"CREATE VIRTUAL TABLE records_fts USING fts5(kind,domain,subdomain,name,authors,cats,summary,tokenize='{tok}')")
    except sqlite3.OperationalError:
        tok = "unicode61"; con.execute(f"CREATE VIRTUAL TABLE records_fts USING fts5(kind,domain,subdomain,name,authors,cats,summary,tokenize='{tok}')")
    con.executemany("INSERT INTO records_fts(kind,domain,subdomain,name,authors,cats,summary) VALUES(?,?,?,?,?,?,?)",
                    [(rw["kind"],rw["domain"],rw["subdomain"],rw["name"],rw["authors"],rw["cats"],rw["summary"]) for rw in rows])
    con.commit(); con.close()
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    L = ["# 知识域结构化索引（kb-structuring）","",f"> 源库：`{ROOT}`  ·  生成：{stamp}",
         f"> 扫描 {nf} 个 JSON（失败 {nbad}）→ 原始 {nraw} 条 → 去重后 **{len(recs)}**（论文 {len(papers)} / 项目 {len(projs)}）","",
         "## 领域总览","","| 知识领域 | 论文 | 项目 | 合计 | 明细 |","|:---|---:|---:|---:|:---|"]
    for d in order: L.append(f"| {d} | {tot(d,'paper')} | {tot(d,'project')} | {tot(d,'paper')+tot(d,'project')} | [by_domain/{san(d)}.md](by_domain/{san(d)}.md) |")
    L += ["","## 产出","","records.json · records.csv/papers.csv/projects.csv · knowledge.db(SQLite+FTS5) · by_domain/*.md · STATS.md",""]
    open(os.path.join(OUT,"INDEX.md"),"w",encoding="utf-8").write("\n".join(L))
    for d in order:
        ps = [r for r in recs if r["domain"] == d and r["kind"] == "paper"]; js = [r for r in recs if r["domain"] == d and r["kind"] == "project"]
        o = [f"# {d}","",f"论文 {len(ps)} · 项目 {len(js)}",""]
        if js:
            o += ["## 项目（⭐降序）","","| # | 仓库 | ⭐ | 语言 | 创建 | 简介 |","|---:|:---|---:|:---|:---|:---|"]
            for i, r in enumerate(sorted(js, key=lambda x: -(x.get("stars") or 0))[:150], 1):
                o.append(f"| {i} | [{r['name']}]({r['url']}) | {r.get('stars') or '-'} | {r.get('language') or '-'} | {r.get('created') or '-'} | {(r.get('description') or '').replace('|','/')[:70]} |")
            if len(js) > 150: o.append(f"| … | 其余 {len(js)-150} 见 records.csv | | | | |")
            o.append("")
        if ps:
            o += ["## 论文（日期降序）","","| # | 标题 | 日期 | ID | 分类 |","|---:|:---|:---|:---|:---|"]
            for i, r in enumerate(sorted(ps, key=lambda x: x.get("date") or "", reverse=True)[:250], 1):
                o.append(f"| {i} | {(r.get('title') or '').replace('|','/')[:95]} | {r.get('date') or '-'} | {r.get('arxiv_id') or '-'} | {', '.join((r.get('cats') or [])[:3])} |")
            if len(ps) > 250: o.append(f"| … | 其余 {len(ps)-250} 见 records.csv | | | |")
            o.append("")
        open(os.path.join(OUT,"by_domain",san(d)+".md"),"w",encoding="utf-8").write("\n".join(o))
    yrs = {}
    for r in papers:
        y = (r.get("date") or "?")[:4]; yrs[y] = yrs.get(y,0) + 1
    S = ["# 知识域结构化 · 统计","",f"> 生成：{stamp}","","| 阶段 | 数量 |","|:---|---:|",f"| 扫描 JSON | {nf} |",f"| 解析失败 | {nbad} |",f"| 跳过 raw 清单 | {nskip} |",
         f"| 原始记录 | {nraw} |",f"| 去重后 | {len(recs)} |",f"| 论文 | {len(papers)} |",f"| 项目 | {len(projs)} |","",
         "## 领域分布","","| 领域 | 论文 | 项目 |","|:---|---:|---:|"]
    for d in order: S.append(f"| {d} | {tot(d,'paper')} | {tot(d,'project')} |")
    S += ["","## 论文年份","","| 年 | 数 |","|:---|---:|"]
    for y in sorted(yrs): S.append(f"| {y} | {yrs[y]} |")
    S += ["","## 口径","","- 领域：目录映射 + 键名主题 + 同义词归并 → 统一分类；未命中→其他/未分类。",
          "- 去重：论文按 arXiv id（无则标题哈希）；项目按 full_name 小写；⭐取最大、摘要取最长。",
          "- 日期：仅保留 2000–2027；扫描时间取自文件名/目录名。",f"- 全文检索：SQLite FTS5（tokenize={tok}）。",""]
    open(os.path.join(OUT,"STATS.md"),"w",encoding="utf-8").write("\n".join(S))
    return len(recs), len(papers), len(projs)

def main():
    t0 = time.time()
    recs, nf, nbad, nraw, nskip = build()
    n, np_, nj = write_out(recs, nf, nbad, nraw, nskip)
    print(f"[kb_domain_structuring] root={ROOT}")
    print(f"  scanned={nf} fail={nbad} skip={nskip} raw={nraw} dedup={n} papers={np_} projects={nj}")
    print(f"  out={OUT} elapsed={time.time()-t0:.1f}s")

if __name__ == "__main__":
    main()
