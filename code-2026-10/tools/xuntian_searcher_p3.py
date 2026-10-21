"""
Store batch of relevant arXiv results
"""
import json, hashlib, re, html
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
    record = {"id": item_id, "type": source_type, "subdir": subdir,
        "title": title[:200], "url": url[:500], "author": author[:100],
        "year": year, "note": note[:500], "abstract": abstract[:2000],
        "collected_at": datetime.now().isoformat()}
    path = base_dir / f"{item_id}_{safe}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    with open(COLLECT_LOG, "r") as f: log = json.load(f)
    ids = {r["id"] for r in log["collections"]}
    if item_id not in ids:
        log["collections"].append({"id": item_id, "type": source_type, "subdir": subdir,
            "title": title[:60], "path": str(path), "ts": datetime.now().isoformat()})
        log["last_run"] = datetime.now().isoformat()
        if len(log["collections"]) > 2000: log["collections"] = log["collections"][-1000:]
        with open(COLLECT_LOG, "w") as f: json.dump(log, f, ensure_ascii=False, indent=2)
        print(f"  [+] {title[:65]}")
        return True
    print(f"  [=] {title[:50]}")
    return False

def fetch_arxiv(category, extra=""):
    query = f"cat:{category}+AND+all:lithium+AND+all:battery"
    if extra:
        query = f"cat:{category}+AND+all:{extra}"
    url = f"https://export.arxiv.org/api/query?search_query={query}&start=0&max_results=8&sortBy=submittedDate&sortOrder=descending"
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Hermes/1.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=25, context=ctx)
        data = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"error": str(e)[:60]}
    if not data.strip():
        return {"error": "Empty"}
    try:
        root = ET.fromstring(data)
    except:
        return {"error": "XML parse"}
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
        results.append({"title": title, "url": url_val, "year": year, "author": author_str})
    return {"results": results, "count": len(results)}

searches = [
    ("cond-mat.mtrl-sci", "", "literature", "prelithiation_paper", "电池材料(cond-mat)"),
    ("physics.app-ph", "", "literature", "prelithiation_paper", "电池物理(app-ph)"),
    ("cond-mat.mtrl-sci", "prelithiation", "literature", "prelithiation_review", "预锂化(cond-mat)"),
    ("physics.chem-ph", "lithium+battery", "literature", "electrolyte", "锂电化学"),
    ("cond-mat.mtrl-sci", "silicon+anode", "literature", "anode_silicon", "硅负极(cond-mat)"),
    ("cond-mat.mtrl-sci", "electrode+manufacturing", "textbook", "battery", "极片制造(cond-mat)"),
]

if __name__ == "__main__":
    if not COLLECT_LOG.exists():
        with open(COLLECT_LOG, "w") as f:
            json.dump({"collections": [], "last_run": None, "version": "1.0"}, f, indent=2)
    
    total_new = 0
    total_dup = 0
    
    for cat, extra, stype, subdir, desc in searches:
        print(f"\n[{desc}] cat:{cat} + {extra or 'lithium battery'}")
        result = fetch_arxiv(cat, extra) if extra else fetch_arxiv(cat)
        if "error" in result:
            print(f"  ✗ {result['error']}")
            continue
        print(f"  Found {result['count']} papers")
        for r in result["results"]:
            stored = store_item(stype, subdir, r["title"], r["url"],
                              r["author"], r["year"], note=desc)
            if stored: total_new += 1
            else: total_dup += 1
    
    print(f"\n{'='*50}")
    print(f"Done: {total_new} new + {total_dup} duplicates")
    print(f"{'='*50}")
