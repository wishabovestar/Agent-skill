"""
巡天物理/陶瓷知识采集器 v1.0 (v3.2新增)
采集固体物理、计算物理、陶瓷科学领域的论文/教材/报告
"""
import json, hashlib, re, html, subprocess, urllib.request, ssl, xml.etree.ElementTree as ET, urllib.parse
from pathlib import Path
from datetime import datetime

DATA_ROOT = Path("D:/hermes/data/physics_knowledge")
COLLECT_LOG = DATA_ROOT / "_collection_log.json"

def store_item(source_type, subdir, title, url, author="", year=0, note="", abstract=""):
    base_dir = DATA_ROOT / source_type / subdir
    base_dir.mkdir(parents=True, exist_ok=True)
    item_id = hashlib.md5(f"{source_type}:{subdir}:{title}".encode()).hexdigest()[:12]
    safe = re.sub(r'[\\/:*?"<>|]', '_', title)[:80]
    record = {
        "id": item_id, "type": source_type, "subdir": subdir,
        "title": title[:200], "url": url[:500], "author": author[:100],
        "year": year, "note": note[:500], "abstract": (abstract or "")[:2000],
        "collected_at": datetime.now().isoformat(),
    }
    path = base_dir / f"{item_id}_{safe}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    with open(COLLECT_LOG, "r") as f: log = json.load(f)
    ids = {r["id"] for r in log["collections"]}
    if item_id not in ids:
        log["collections"].append({
            "id": item_id, "type": source_type, "subdir": subdir,
            "title": title[:60], "path": str(path), "ts": datetime.now().isoformat(),
        })
        log["last_run"] = datetime.now().isoformat()
        if len(log["collections"]) > 2000: log["collections"] = log["collections"][-1000:]
        with open(COLLECT_LOG, "w") as f: json.dump(log, f, ensure_ascii=False, indent=2)
        print(f"  [+] {title[:65]}")
        return True
    print(f"  [=] {title[:50]}")
    return False

def search_arxiv(query, max_results=8):
    url = "https://export.arxiv.org/api/query?search_query=" + urllib.parse.quote(query, safe='+&') + f"&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Hermes/1.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=25, context=ctx)
        data = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"error": str(e)[:60]}
    if not data.strip(): return {"error": "Empty"}
    try: root = ET.fromstring(data)
    except: return {"error": "XML parse"}
    ns = {"a": "http://www.w3.org/2005/Atom"}
    results = []
    for entry in root.findall("a:entry", ns):
        title_el = entry.find("a:title", ns)
        title = html.unescape(title_el.text.strip().replace("\n"," ").replace("  "," ")) if title_el is not None else ""
        url_el = entry.find("a:id", ns)
        id_part = url_el.text.split("/")[-1] if url_el is not None else ""
        url_val = f"https://arxiv.org/abs/{id_part}"
        pub = entry.find("a:published", ns)
        year = int(pub.text[:4]) if pub is not None else 0
        authors = [a.find("a:name", ns).text for a in entry.findall("a:author", ns)]
        author_str = ", ".join(authors[:3])
        summ = entry.find("a:summary", ns)
        summary = html.unescape(summ.text.strip().replace("\n"," ")[:400]) if summ is not None else ""
        results.append({"title": title, "url": url_val, "year": year, "author": author_str, "abstract": summary})
    return {"results": results, "count": len(results)}

# ===== 知识源定义 =====
SOURCES = {
    "literature": {
        "dir": "literature",
        "subdirs": {
            "physics_solid": "固体物理/凝聚态",
            "physics_computational": "计算物理/DFT",
            "ceramics_sintering": "陶瓷烧结",
            "ceramics_mechanical": "陶瓷力学/热学",
            "ceramics_dielectric": "介电/铁电陶瓷",
            "ceramics_advanced": "先进陶瓷(Al2O3/ZrO2/SiC)",
        }
    },
    "textbooks": {
        "dir": "textbooks",
        "subdirs": {
            "solid_state": "固体物理教材",
            "ceramics": "陶瓷工程教材",
            "computational_physics": "计算物理教材",
        }
    },
    "reports": {
        "dir": "reports",
        "subdirs": {
            "ceramics_industry": "陶瓷行业报告",
        }
    }
}

# ===== 搜索计划 =====
SEARCHES = [
    # 固体物理
    ("arxiv", "cat:cond-mat.mtrl-sci+AND+all:solid+state+AND+all:physics", "literature", "physics_solid", "固体物理"),
    ("arxiv", "cat:cond-mat.mtrl-sci+AND+all:ceramics+AND+all:dielectric", "literature", "ceramics_dielectric", "介电陶瓷"),
    ("arxiv", "cat:cond-mat.mtrl-sci+AND+all:ceramics+AND+all:sintering", "literature", "ceramics_sintering", "陶瓷烧结"),
    ("arxiv", "cat:cond-mat.mtrl-sci+AND+all:ceramic+AND+all:mechanical", "literature", "ceramics_mechanical", "陶瓷力学"),
    ("arxiv", "cat:cond-mat.mtrl-sci+AND+all:alumina+AND+all:ceramic", "literature", "ceramics_advanced", "氧化铝陶瓷"),
    ("arxiv", "cat:cond-mat.mtrl-sci+AND+all:zirconia+AND+all:ceramic", "literature", "ceramics_advanced", "氧化锆陶瓷"),
    ("arxiv", "cat:cond-mat.mtrl-sci+AND+all:\"silicon+carbide\"+AND+all:ceramic", "literature", "ceramics_advanced", "碳化硅陶瓷"),
    ("arxiv", "cat:physics.app-ph+AND+all:ceramic+AND+all:thermal+AND+all:conductivity", "literature", "ceramics_mechanical", "陶瓷热导率"),
    ("arxiv", "all:density+functional+theory+AND+all:molecular+dynamics+AND+all:ceramic", "literature", "physics_computational", "DFT/分子动力学"),
    ("arxiv", "cat:cond-mat.mtrl-sci+AND+all:MAX+phase+AND+all:ceramic", "literature", "ceramics_advanced", "MAX相陶瓷"),
    ("arxiv", "cat:cond-mat.mtrl-sci+AND+all:ferroelectric+AND+all:ceramic", "literature", "ceramics_dielectric", "铁电陶瓷"),
    ("arxiv", "cat:cond-mat.mtrl-sci+AND+all:ceramic+AND+all:composite", "literature", "ceramics_mechanical", "陶瓷复合材料"),
]

if __name__ == "__main__":
    import sys
    if not COLLECT_LOG.exists():
        with open(COLLECT_LOG, "w") as f:
            json.dump({"collections": [], "last_run": None, "version": "1.0"}, f, indent=2)

    # Init directories
    for stype, info in SOURCES.items():
        for subdir in info["subdirs"]:
            (DATA_ROOT / info["dir"] / subdir).mkdir(parents=True, exist_ok=True)

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(SEARCHES)
    searches = SEARCHES[:limit]
    total_new = 0

    for engine, query, stype, subdir, desc in searches:
        print(f"\n[{desc}] {stype}/{subdir}")
        r = search_arxiv(query)
        if "error" in r:
            print(f"  ✗ {r['error']}")
            continue
        print(f"  Found {r['count']} papers")
        for p in r["results"]:
            if store_item(stype, subdir, p["title"], p["url"],
                         p["author"], p["year"], note=desc, abstract=p.get("abstract","")):
                total_new += 1

    # Generate routing
    routing = {
        "_version": "1.0", "_source": "physics_ceramics_collector",
        "_updated": datetime.now().isoformat(),
        "routing": [
            {"source": "literature/physics_solid", "target_agents": ["通量", "算渊"], "reason": "固体物理/凝聚态"},
            {"source": "literature/physics_computational", "target_agents": ["算渊", "通量"], "reason": "计算物理/DFT"},
            {"source": "literature/ceramics_sintering", "target_agents": ["程实", "伏安"], "reason": "陶瓷烧结工艺"},
            {"source": "literature/ceramics_mechanical", "target_agents": ["构形", "程实"], "reason": "陶瓷力学/热学"},
            {"source": "literature/ceramics_dielectric", "target_agents": ["伏安", "通量"], "reason": "介电/铁电陶瓷"},
            {"source": "literature/ceramics_advanced", "target_agents": ["程实", "构形"], "reason": "先进陶瓷"},
            {"source": "textbooks/solid_state", "target_agents": ["通量", "算渊"], "reason": "固体物理教材"},
            {"source": "textbooks/ceramics", "target_agents": ["程实"], "reason": "陶瓷教材"},
            {"source": "reports/ceramics_industry", "target_agents": ["程实", "运筹"], "reason": "陶瓷行业报告"},
        ]
    }
    with open(DATA_ROOT / "_routing.json", "w", encoding="utf-8") as f:
        json.dump(routing, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Routing written to {DATA_ROOT / '_routing.json'}")

    print(f"\n{'='*50}")
    print(f"Done: {total_new} new items")
    print(f"Storage: {DATA_ROOT}")
    print(f"{'='*50}")
