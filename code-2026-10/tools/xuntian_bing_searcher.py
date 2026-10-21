"""
xuntian_bing_searcher.py — Search Bing International via SOCKS5 proxy
"""
import re, json, html, sys

def search_bing(query, use_proxy=True):
    import urllib.request, ssl
    from urllib.parse import quote
    
    url = f"https://www.bing.com/search?q={quote(query)}&setlang=en-US"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    try:
        if use_proxy:
            proxy = urllib.request.ProxyHandler({
                "http": "socks5://127.0.0.1:10808",
                "https": "socks5://127.0.0.1:10808"
            })
            opener = urllib.request.build_opener(proxy)
            resp = opener.open(req, timeout=20, context=ctx)
        else:
            resp = urllib.request.urlopen(req, timeout=20, context=ctx)
        content = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"error": str(e)}
    
    # Extract results — try multiple patterns
    results = []
    seen = set()
    
    # Pattern 1: Standard h2 > a with href
    for m in re.finditer(r'<h2[^>]*>(.*?)</h2>', content, re.DOTALL):
        h2 = m.group(1)
        a = re.search(r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', h2, re.DOTALL)
        if not a:
            continue
        url_str = a.group(1)
        title = re.sub(r'<[^>]+>', '', a.group(2))
        title = html.unescape(title).strip()
        if not title or len(title) < 8:
            continue
        # Skip navigation/results page links
        if 'bing.com' in url_str.lower() or 'go.microsoft.com' in url_str.lower():
            continue
        # Clean URL
        if '&' in url_str:
            url_str = url_str.split('&')[0]
        key = (title[:40], url_str[:60])
        if key in seen:
            continue
        seen.add(key)
        results.append({"title": title, "url": url_str})
    
    # Pattern 2: <a> with cite parent (Bing format)
    if len(results) < 3:
        for m in re.finditer(r'<cite[^>]*>(.*?)</cite>', content, re.DOTALL):
            cite = m.group(1)
            url_match = re.search(r'href="(https?://[^"]+)"', content[max(0, m.start()-500):m.start()])
            if url_match:
                url_str = url_match.group(1)
                if 'bing.com' in url_str.lower():
                    continue
                if '&' in url_str:
                    url_str = url_str.split('&')[0]
                results.append({"title": html.unescape(cite).strip()[:80], "url": url_str})
                if len(results) >= 8:
                    break
    
    return {"results": results[:8], "query": query, "count": len(results)}


def store_result(source_type, subdir, title, url, author="", year=0, note=""):
    """Store a result into the book_knowledge database"""
    import json, hashlib
    from pathlib import Path
    from datetime import datetime
    
    DATA_ROOT = Path("D:/hermes/data/book_knowledge")
    COLLECT_LOG = DATA_ROOT / "_collection_log.json"
    
    source_map = {
        "prelithiation_review": ("literature", "prelithiation_review"),
        "prelithiation_paper": ("literature", "prelithiation_paper"),
        "anode_silicon": ("literature", "anode_silicon"),
        "cathode_lco": ("literature", "cathode_lco"),
        "industry_report": ("report", "industry"),
        "broker_report": ("report", "broker"),
        "battery_textbook": ("textbook", "battery"),
        "silicon_anode": ("literature", "anode_silicon"),
    }
    
    stype, sdir = source_map.get(source_type, ("literature", "general"))
    base_dir = DATA_ROOT / sdir
    base_dir.mkdir(parents=True, exist_ok=True)
    
    item_id = hashlib.md5(f"{stype}:{sdir}:{title}".encode()).hexdigest()[:12]
    safe = re.sub(r'[\\/:*?"<>|]', '_', title)[:80]
    
    record = {
        "id": item_id, "type": stype, "subdir": sdir,
        "title": title[:200], "url": url[:500],
        "author": author[:100] if author else "",
        "year": year, "note": note[:2000],
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
            "id": item_id, "type": stype, "subdir": sdir,
            "title": title[:60], "path": str(path),
            "ts": datetime.now().isoformat(),
        })
        log["last_run"] = datetime.now().isoformat()
        if len(log["collections"]) > 2000:
            log["collections"] = log["collections"][-1000:]
        with open(COLLECT_LOG, "w") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
        print(f"  📥 Stored: [{stype}/{sdir}] {title[:60]}")
        return True
    else:
        print(f"  ⏭️  Already exists: {title[:50]}")
        return False


# ===== P0/P1 Search Plan =====
SEARCH_PLAN = [
    # === P0 — 预锂化综述 ===
    {"query": "prelithiation review lithium battery", "type": "prelithiation_review", "note": "预锂化综述(英)"},
    {"query": "pre-lithiation strategies review 2024 2025", "type": "prelithiation_review", "note": "预锂化策略综述"},
    {"query": "prelithiation methods for high energy lithium ion batteries review", "type": "prelithiation_review", "note": "高能锂电池预锂化方法"},
    
    # === P0 — 预锂化研究论文 ===
    {"query": "prelithiation silicon anode high capacity", "type": "prelithiation_paper", "note": "硅负极预锂化"},
    {"query": "Li5FeO4 cathode prelithiation additive", "type": "prelithiation_paper", "note": "Li5FeO4补锂剂"},
    {"query": "electrochemical prelithiation lithium ion battery", "type": "prelithiation_paper", "note": "电化学预锂化"},
    
    # === P0 — 研报/行业报告 ===
    {"query": "lithium battery prelithiation market report 2025", "type": "broker_report", "note": "预锂化市场研报"},
    {"query": "battery prelithiation technology industry report whitepaper", "type": "industry_report", "note": "预锂化行业报告"},
    
    # === P0 — 教材 ===
    {"query": "lithium ion battery textbook principles electrochemistry", "type": "battery_textbook", "note": "锂电池教材"},
    {"query": "advanced lithium battery textbook manufacturing", "type": "battery_textbook", "note": "电池制造教材"},
    
    # === P1 — 硅负极 ===
    {"query": "silicon carbon composite anode review 2024 2025", "type": "silicon_anode", "note": "硅碳负极综述"},
    {"query": "prelithiated silicon oxide anode lithium battery", "type": "silicon_anode", "note": "预锂化氧化亚硅"},
]


if __name__ == "__main__":
    import sys
    
    run_all = len(sys.argv) < 2 or sys.argv[1] == "all"
    if run_all:
        plan = SEARCH_PLAN
        print(f"🚀 Running ALL {len(plan)} searches...")
    else:
        n = int(sys.argv[1])
        plan = SEARCH_PLAN[:n]
        print(f"🚀 Running first {n} searches...")
    
    total_new = 0
    for i, task in enumerate(plan, 1):
        print(f"\n[{i}/{len(plan)}] {task['note']}")
        print(f"  Query: {task['query']}")
        
        # Try with proxy first, fallback to direct
        result = search_bing(task["query"], use_proxy=True)
        if "error" in result:
            print(f"  Proxy failed: {result['error'][:60]}")
            print(f"  Retrying direct...")
            result = search_bing(task["query"], use_proxy=False)
        
        if "error" in result:
            print(f"  ❌ Search failed: {result['error'][:80]}")
            continue
        
        print(f"  Found {result['count']} results")
        for r in result["results"]:
            print(f"    {r['title'][:70]}")
            print(f"    -> {r['url'][:80]}")
            # Store each result
            stored = store_result(
                source_type=task["type"],
                subdir=task["type"].replace("_report", "").replace("_textbook", ""),
                title=r["title"],
                url=r["url"],
                note=task["note"]
            )
            if stored:
                total_new += 1
    
    print(f"\n{'='*50}")
    print(f"✅ Search complete: {total_new} new items stored")
    print(f"{'='*50}")
