"""
xuntian_searcher.py — Phase 2: remaining arXiv queries + Bing
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
        log["collections"].append({"id": item_id, "type": source_type, "subdir": subdir, "title": title[:60], "path": str(path), "ts": datetime.now().isoformat()})
        log["last_run"] = datetime.now().isoformat()
        if len(log["collections"]) > 2000: log["collections"] = log["collections"][-1000:]
        with open(COLLECT_LOG, "w") as f: json.dump(log, f, ensure_ascii=False, indent=2)
        print(f"  [+] {title[:65]}")
        return True
    print(f"  [=] {title[:50]}")
    return False

def search_arxiv(query, max_results=10):
    url = "https://export.arxiv.org/api/query?search_query=" + urllib.parse.quote(query, safe='+&') + f"&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Hermes/1.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=25, context=ctx)
        data = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"error": str(e)[:80]}
    if not data.strip(): return {"error": "Empty"}
    try:
        root = ET.fromstring(data)
    except:
        return {"error": "XML parse"}
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

def search_bing_curl(query, max_results=6):
    """Search Bing International via proxy"""
    encoded = urllib.parse.quote(query)
    cmd = f'curl -s --socks5 127.0.0.1:10808 "https://www.bing.com/search?q={encoded}&setlang=en-US&count={max_results}" -H "User-Agent: Mozilla/5.0" -m 20 2>nul'
    try:
        out = subprocess.check_output(cmd, shell=True, timeout=25, text=True, stderr=subprocess.DEVNULL)
    except:
        return {"error": "curl failed"}
    results = []
    seen = set()
    # Extract b_algo blocks
    blocks = re.findall(r'<li class="b_algo[^"]*"[^>]*>(.*?)</li>', out, re.DOTALL)
    for block in blocks:
        h2 = re.search(r'<h2[^>]*><a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a></h2>', block, re.DOTALL)
        if not h2:
            continue
        url = h2.group(1).split('&')[0]
        title = re.sub(r'<[^>]+>', '', h2.group(2)).strip()
        title = html.unescape(title)
        if 'bing.com' in url.lower() or title in seen:
            continue
        seen.add(title)
        results.append({"title": title, "url": url})
        if len(results) >= max_results:
            break
    return {"results": results, "count": len(results)}

# Phase 2 queries
SEARCHES_P2 = [
    # Remaining arXiv queries (fixed)
    ("arxiv", "all:silicon+oxide+anode+battery", "silicon oxide anode", "literature", "anode_silicon", "氧化亚硅负极"),
    ("arxiv", "all:lithium+ion+battery+cycle+life+review", "battery cycle life review", "literature", "battery_aging", "循环寿命综述"),
    ("arxiv", "all:Li5FeO4+cathode+prelithiation", "Li5FeO4 cathode", "literature", "cathode_lco", "Li5FeO4研究"),
    ("arxiv", "all:silicon+carbon+composite+anode+lithium", "Si-C composite anode", "literature", "anode_silicon", "硅碳负极"),
    ("arxiv", "all:silicon+anode+degradation+review", "Si anode degradation", "literature", "anode_silicon", "硅负极退化"),
    ("arxiv", "all:prelithiation+review+lithium+ion+battery", "prelithiation review", "literature", "prelithiation_review", "预锂化综述二"),
    ("arxiv", "all:solid+electrolyte+interface+SEI+lithium", "SEI formation lithium", "literature", "electrolyte", "SEI界面"),
    ("arxiv", "all:lithium+battery+manufacturing+process", "battery manufacturing", "textbook", "battery", "电池制造工艺"),
    ("arxiv", "all:battery+electrode+engineering+textbook", "electrode engineering", "textbook", "battery", "极片工程"),
    
    # Bing searches via proxy
    ("bing", "prelithiation technology lithium battery market report", "prelithiation market report", "report", "broker", "预锂化市场研报"),
    ("bing", "lithium battery industry report 2025", "lithium industry report", "report", "industry", "锂电池行业报告"),
    ("bing", "lithium ion battery textbook principles electrochemistry", "battery textbook", "textbook", "battery", "锂电池教材"),
]

if __name__ == "__main__":
    import sys
    
    if not COLLECT_LOG.exists():
        with open(COLLECT_LOG, "w") as f:
            json.dump({"collections": [], "last_run": None, "version": "1.0"}, f, indent=2)
    
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(SEARCHES_P2)
    searches = SEARCHES_P2[:limit]
    
    total_new = 0
    total_dup = 0
    
    for engine, query, label, stype, subdir, desc in searches:
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
                                    note=desc, abstract=r.get("abstract",""))
                if stored: total_new += 1
                else: total_dup += 1
        elif engine == "bing":
            result = search_bing_curl(query)
            if "error" in result:
                print(f"  ✗ {result['error']}")
                continue
            print(f"  Found {result['count']} results")
            for r in result["results"]:
                stored = store_item(stype, subdir, r["title"], r["url"],
                                    note=desc)
                if stored: total_new += 1
                else: total_dup += 1
    
    print(f"\n{'='*50}")
    print(f"DONE: {total_new} new + {total_dup} duplicates")
    print(f"{'='*50}")
