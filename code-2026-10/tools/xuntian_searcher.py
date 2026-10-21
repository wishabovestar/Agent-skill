"""
xuntian_searcher.py v2 — arXiv + Bing searches for book knowledge
"""
import json, hashlib, re, html, subprocess, urllib.parse
from pathlib import Path
from datetime import datetime
import urllib.request, ssl, xml.etree.ElementTree as ET

DATA_ROOT = Path("D:/hermes/data/book_knowledge")
COLLECT_LOG = DATA_ROOT / "_collection_log.json"

def store_item(source_type, subdir, title, url, author="", year=0, note="", abstract=""):
    base_dir = DATA_ROOT / source_type / subdir
    base_dir.mkdir(parents=True, exist_ok=True)
    item_id = hashlib.md5(f"{source_type}:{subdir}:{title}".encode()).hexdigest()[:12]
    safe = re.sub(r'[\\/:*?"<>|]', '_', title)[:80]
    record = {
        "id": item_id, "type": source_type, "subdir": subdir,
        "title": title[:200], "url": url[:500], "author": author[:100],
        "year": year, "note": note[:500], "abstract": abstract[:2000],
        "collected_at": datetime.now().isoformat(),
    }
    path = base_dir / f"{item_id}_{safe}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    with open(COLLECT_LOG, "r") as f:
        log = json.load(f)
    ids = {r["id"] for r in log["collections"]}
    if item_id not in ids:
        log["collections"].append({
            "id": item_id, "type": source_type, "subdir": subdir,
            "title": title[:60], "path": str(path),
            "ts": datetime.now().isoformat(),
        })
        log["last_run"] = datetime.now().isoformat()
        if len(log["collections"]) > 2000:
            log["collections"] = log["collections"][-1000:]
        with open(COLLECT_LOG, "w") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
        print(f"  [+] {title[:65]}")
        return True
    print(f"  [=] {title[:50]}")
    return False

def search_arxiv(query, max_results=10):
    url = f"https://export.arxiv.org/api/query?search_query={query}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Hermes/1.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=25, context=ctx)
        data = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"error": str(e)[:80]}
    if not data.strip():
        return {"error": "Empty response"}
    try:
        root = ET.fromstring(data)
    except:
        return {"error": "XML parse failed"}
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    results = []
    for entry in root.findall("a:entry", ns):
        title_el = entry.find("a:title", ns)
        title = html.unescape(title_el.text.strip().replace("\n"," ").replace("  "," ")) if title_el is not None else ""
        url_el = entry.find("a:id", ns)
        url_val = url_el.text if url_el is not None else ""
        pub = entry.find("a:published", ns)
        year = int(pub.text[:4]) if pub is not None else 0
        authors = [a.find("a:name", ns).text for a in entry.findall("a:author", ns)]
        author_str = ", ".join(authors[:3])
        summ = entry.find("a:summary", ns)
        summary = html.unescape(summ.text.strip().replace("\n"," ")[:300]) if summ is not None else ""
        results.append({"title": title, "url": url_val, "year": year, "author": author_str, "abstract": summary})
    return {"results": results, "count": len(results)}


# ===== SEARCH PLAN =====
SEARCHES = [
    # === arXiv P0 ===
    "arxiv|all:prelithiation+AND+all:review|lithium battery prelithiation review|literature|prelithiation_review|预锂化综述",
    "arxiv|all:prelithiation+AND+all:silicon+AND+all:anode|Si anode prelithiation|literature|prelithiation_paper|硅负极预锂化",
    "arxiv|all:lithium+AND+all:prelithiation+AND+all:cathode|prelithiation cathode|literature|cathode_lco|正极补锂",
    "arxiv|all:\"silicon+oxide\"+AND+all:anode+AND+all:battery|silicon oxide anode|literature|anode_silicon|氧化亚硅负极",
    "arxiv|all:lithium+AND+all:battery+AND+all:manufacturing+AND+all:anode|battery manufacturing anode|literature|prelithiation_paper|电池制造负极",
    "arxiv|all:battery+AND+all:textbook+AND+all:review+battery+AND+all:education|battery textbook|textbook|battery|电池教材",
    "arxiv|all:lithium+AND+all:\"solid+electrolyte\"+AND+all:battery|solid electrolyte battery|literature|electrolyte|固态电解质",
    "arxiv|all:\"cycle+life\"+AND+all:lithium+AND+all:battery+AND+all:review|battery cycle life review|literature|battery_aging|电池循环寿命",
    "arxiv|all:\"silicon+carbon\"+AND+all:composite+AND+all:anode|Si-C composite anode|literature|anode_silicon|硅碳复合负极",
    "arxiv|all:battery+AND+all:electrode+AND+all:manufacturing+AND+all:process|battery electrode manufacturing|textbook|battery|电池极片制造",
    "arxiv|all:Li5FeO4+AND+all:lithium|Li5FeO4 cathode additive|literature|cathode_lco|Li5FeO4研究",
    "arxiv|all:electrochemical+AND+all:prelithiation+AND+all:method|electrochemical prelithiation|literature|prelithiation_paper|电化学预锂化",
    "arxiv|cat:cond-mat.mtrl-sci+AND+all:lithium+AND+all:battery+AND+all:degradation|battery degradation materials|literature|battery_aging|电池退化材料",
    "arxiv|all:lithium+AND+all:\"silicon+anode\"+AND+all:degradation|silicon anode degradation|literature|anode_silicon|硅负极退化",
]

if __name__ == "__main__":
    import sys
    
    if not COLLECT_LOG.exists():
        with open(COLLECT_LOG, "w") as f:
            json.dump({"collections": [], "last_run": None, "version": "1.0"}, f, indent=2)
    
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(SEARCHES)
    searches = SEARCHES[:limit]
    
    total_new = 0
    total_dup = 0
    
    for line in searches:
        parts = line.split("|")
        engine = parts[0]
        query = parts[1]
        label = parts[2]
        stype = parts[3]
        subdir = parts[4]
        desc = parts[5]
        
        print(f"\n{'='*50}")
        print(f"[{engine}] {desc}")
        print(f"  {label}")
        print(f"{'='*50}")
        
        if engine == "arxiv":
            result = search_arxiv(query)
            if "error" in result:
                print(f"  ✗ {result['error']}")
                continue
            print(f"  Found {result['count']} papers")
            for r in result["results"]:
                stored = store_item(stype, subdir, r["title"], r["url"],
                                    r["author"], r["year"],
                                    note=desc,
                                    abstract=r.get("abstract",""))
                if stored: total_new += 1
                else: total_dup += 1
    
    print(f"\n{'='*50}")
    print(f"✅ DONE: {total_new} new + {total_dup} duplicates")
    print(f"📁 Location: {DATA_ROOT}")
    print(f"{'='*50}")
