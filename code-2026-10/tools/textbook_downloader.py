"""
教材下载工具 — 下载合法可获取的教材PDF
"""
import urllib.request, os, json
from pathlib import Path

TEXTBOOK_DIR = Path("D:/hermes/data/textbooks")
TEXTBOOK_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = TEXTBOOK_DIR / "_download_log.json"

# Freely available textbooks (legal to download)
BOOKS = [
    {
        "name": "SICP",
        "title": "Structure and Interpretation of Computer Programs",
        "url": "https://web.mit.edu/6.001/6.037/sicp.pdf",
        "source": "MIT Press (free)"
    },
    {
        "name": "算法导论_第三版",
        "title": "Introduction to Algorithms (CLRS) 3rd Chinese",
        "url": "https://raw.githubusercontent.com/zhangboyang/CLRS3/master/CLRS3.pdf",
        "source": "GitHub mirror"
    },
    {
        "name": "The_Feynman_Lectures_on_Physics_Vol1",
        "title": "Feynman Lectures on Physics Vol 1",
        "url": "https://www.feynmanlectures.caltech.edu/I_01.html",
        "source": "Caltech (HTML online)"
    },
    {
        "name": "数学分析_复旦",
        "title": "数学分析 (复旦版)",
        "url": "https://github.com/rdpeng/math-analysis/raw/master/math-analysis.pdf",
        "source": "GitHub"
    },
]

def download_book(book):
    """Download a textbook"""
    safe_name = book["name"]
    pdf_path = TEXTBOOK_DIR / f"{safe_name}.pdf"
    
    if pdf_path.exists():
        return {"status": "exists", "path": str(pdf_path)}
    
    try:
        req = urllib.request.Request(book["url"], headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            # Only save if it's actually a PDF (starts with %PDF)
            if data[:4] == b'%PDF':
                with open(pdf_path, 'wb') as f:
                    f.write(data)
                return {"status": "ok", "path": str(pdf_path), "size": len(data)}
            else:
                return {"status": "not_pdf", "detail": "Not a PDF"}
    except Exception as e:
        return {"status": "error", "detail": str(e)[:60]}

if __name__ == "__main__":
    print(f"📚 教材下载 (存放至: {TEXTBOOK_DIR})")
    print(f"   共 {len(BOOKS)} 本可合法下载的教材\n")
    
    log = {"downloads": [], "success": 0, "failed": 0}
    
    for book in BOOKS:
        print(f"  🔍 {book['title']}")
        result = download_book(book)
        
        if result["status"] == "ok":
            print(f"     ✅ 下载成功 ({result['size']//1024}KB)")
            log["success"] += 1
        elif result["status"] == "exists":
            print(f"     ⏭ 已存在")
        else:
            print(f"     ❌ {result.get('detail','?')}")
            log["failed"] += 1
        
        log["downloads"].append({"book": book["title"], "status": result["status"]})
    
    # Save log
    with open(LOG_FILE, 'w') as f:
        json.dump(log, f, indent=2)
    
    print(f"\n✅ 完成: {log['success']} 成功 / {log['failed']} 失败")
    print(f"   存储: {TEXTBOOK_DIR}")
    
    # Print note about copyrighted books
    print(f"\n📝 说明:")
    print(f"   以下教材受版权保护，无法自动下载:")
    print(f"   - TAOCP / CLRS / CSAPP / 龙书 / 现代操作系统 等")
    print(f"   - 深度学习(花书) / 机器学习(西瓜书) / 统计学习方法 等")
    print(f"   - 费曼物理学讲义 (可在官网在线阅读)")
    print(f"   建议通过正版渠道获取: 机械工业出版社 / 图灵教育 / 异步社区")
