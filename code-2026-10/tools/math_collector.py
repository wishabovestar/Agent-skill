"""
数学组知识采集器 — 巡天扩展
从arXiv/维基等源采集数学/算法/统计知识，存入本地数据库
"""
import json, os, re, time
from pathlib import Path
from datetime import datetime

DB_ROOT = Path("D:/hermes/data/math_knowledge")
COLLECT_LOG = DB_ROOT / "collection_log.json"

def init_db():
    """Initialize the math knowledge database structure"""
    for d in ["concepts", "theorems", "algorithms", "papers", "code"]:
        (DB_ROOT / d).mkdir(parents=True, exist_ok=True)
    if not COLLECT_LOG.exists():
        with open(COLLECT_LOG, "w") as f:
            json.dump({"collections": [], "last_updated": None}, f)
    print(f"✅ Math DB at: {DB_ROOT}")

def store_paper(title, authors, abstract, url, domain, source="arxiv"):
    """Store a paper into the math knowledge base"""
    safe_name = re.sub(r'[\/:*?"<>|]', '_', title)[:80]
    record = {
        "title": title, "authors": authors, "abstract": abstract[:500],
        "url": url, "domain": domain, "source": source,
        "collected_at": datetime.now().isoformat(),
    }
    path = DB_ROOT / "papers" / f"{safe_name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    # Log
    with open(COLLECT_LOG, "r") as f: log = json.load(f)
    log["collections"].append({"title": title[:60], "domain": domain, "path": str(path), "ts": datetime.now().isoformat()})
    log["last_updated"] = datetime.now().isoformat()
    with open(COLLECT_LOG, "w") as f: json.dump(log, f, ensure_ascii=False, indent=2)
    print(f"  Stored: {title[:60]}...")
    return path

def store_concept(name, definition, formulas, domain):
    """Store a mathematical concept"""
    safe = re.sub(r'[\/:*?"<>|]', '_', name)[:60]
    record = {"name": name, "definition": definition, "formulas": formulas, "domain": domain,
              "stored_at": datetime.now().isoformat()}
    path = DB_ROOT / "concepts" / f"{safe}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(f"  Concept stored: {name}")
    return path

def stats():
    """Show collection statistics"""
    counts = {}
    for d in ["concepts", "theorems", "algorithms", "papers", "code"]:
        count = len(list((DB_ROOT / d).glob("*.*"))) if (DB_ROOT / d).exists() else 0
        counts[d] = count
    return counts

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "init":
        init_db()
    elif cmd == "stats":
        s = stats()
        print(f"Math Knowledge DB: {json.dumps(s)}")
        print(f"Location: {DB_ROOT}")
