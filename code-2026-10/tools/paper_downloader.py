"""
论文PDF下载引擎 — 从arXiv批量下载已采集论文到本地
"""
import json, re, urllib.request, os, time
from pathlib import Path

PDF_STORAGE = Path("D:/hermes/data/papers")
PDF_STORAGE.mkdir(parents=True, exist_ok=True)
LOG = PDF_STORAGE / "_download_log.json"

# Paper sources to scan
SOURCES = [
    Path("D:/hermes/data/math_knowledge/papers"),
    Path("D:/hermes/data/agent_knowledge/算法"),
]

def extract_arxiv_id(url):
    """Extract arXiv ID from URL"""
    m = re.search(r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+)', url)
    return m.group(1) if m else None

def download_pdf(arxiv_id, title):
    """Download PDF from arXiv"""
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', title)[:60].strip()
    pdf_path = PDF_STORAGE / f"{arxiv_id}_{safe_name}.pdf"
    
    # Check if already downloaded
    if pdf_path.exists():
        return {"status": "exists", "path": str(pdf_path)}
    
    try:
        req = urllib.request.Request(pdf_url, headers={'User-Agent': 'Hermes/1.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            with open(pdf_path, 'wb') as f:
                f.write(data)
            return {"status": "ok", "path": str(pdf_path), "size": len(data)}
    except Exception as e:
        return {"status": "error", "detail": str(e)[:60]}

def scan_and_download():
    """Scan all paper sources and download PDFs"""
    log = {"downloads": [], "total": 0, "success": 0, "failed": 0}
    
    all_papers = []
    
    # Scan math knowledge papers
    for f in SOURCES[0].glob("*.json"):
        with open(f) as fh:
            data = json.load(fh)
        title = data.get("title", f.stem)
        url = data.get("url", "")
        all_papers.append({"title": title, "url": url, "source": "math_knowledge"})
    
    # Scan algorithm papers (each file has a 'papers' array)
    for f in SOURCES[1].glob("*.json"):
        if f.name == "_collection_log.json":
            continue
        with open(f) as fh:
            data = json.load(fh)
        topic = data.get("topic", data.get("algorithm", f.stem))
        papers = data.get("papers", [])
        for p in papers:
            title = p.get("title", "")
            url = p.get("url", "")
            all_papers.append({"title": title, "url": url, "source": f"算法/{topic}"})
    
    print(f"📚 共发现 {len(all_papers)} 篇论文引用")
    
    # Download each
    for i, p in enumerate(all_papers):
        arxiv_id = extract_arxiv_id(p["url"])
        if not arxiv_id:
            continue
        
        result = download_pdf(arxiv_id, p["title"])
        
        if result["status"] == "ok":
            print(f"  ✅ [{i+1}/{len(all_papers)}] {p['title'][:50]}... ({result['size']//1024}KB)")
            log["success"] += 1
        elif result["status"] == "exists":
            print(f"  ⏭ [{i+1}/{len(all_papers)}] 已存在: {p['title'][:40]}")
        else:
            print(f"  ❌ [{i+1}/{len(all_papers)}] {p['title'][:40]}: {result.get('detail','?')}")
            log["failed"] += 1
        
        log["downloads"].append({"title": p["title"], "arxiv_id": arxiv_id, "status": result["status"]})
        log["total"] += 1
        time.sleep(3)  # Be nice to arXiv
    
    # Save log
    with open(LOG, 'w') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 下载完成: {log['success']} 成功 / {log['failed']} 失败")
    print(f"   存储: {PDF_STORAGE}")
    return log

if __name__ == "__main__":
    scan_and_download()
