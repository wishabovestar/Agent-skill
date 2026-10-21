#!/usr/bin/env python3
"""
巡天知识采集扩展 v4.0 — 教材/文献/报告/图灵系列
存储位置:
  D:/hermes/data/textbooks/     → 教材
  D:/hermes/data/literature/    → 文献/论文/综述
  D:/hermes/data/reports/       → 研究报告/行业报告
  D:/hermes/data/books/turing/  → 图灵系列图书
"""
import json, os, re, hashlib, sys, time
from pathlib import Path
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError
import ssl

# ── 路径 ──
ROOT = Path("D:/hermes/data")
DIRS = {
    "textbook": ROOT / "textbooks",
    "literature": ROOT / "literature",
    "report": ROOT / "reports",
    "book_turing": ROOT / "books" / "turing",
    "book_cs": ROOT / "books" / "cs-classics",
    "book_math": ROOT / "books" / "math-classics",
}
COLLECT_LOG = ROOT / "_edu_collection_log.json"
SSL_CTX = ssl._create_unverified_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# ── 图灵系列图书基础库 (核心书目) ──
TURING_BOOKS = [
    # === 计算机科学 ===
    {"title": "计算机程序设计艺术 (TAOCP)", "author": "Donald E. Knuth", "volumes": 4, "isbn": "978-7-115-xxxxx", "tag": "algorithm,classics"},
    {"title": "算法导论 (CLRS)", "author": "Thomas H. Cormen", "isbn": "978-7-115-xxxxx", "tag": "algorithm,textbook"},
    {"title": "深入理解计算机系统 (CSAPP)", "author": "Randal E. Bryant", "isbn": "978-7-115-xxxxx", "tag": "cs,classics"},
    {"title": "结构化和解计算机程序 (SICP)", "author": "Harold Abelson", "isbn": "978-7-115-xxxxx", "tag": "cs,classics,lisp"},
    {"title": "编译原理 (龙书)", "author": "Alfred V. Aho", "isbn": "978-7-115-xxxxx", "tag": "compiler,classics"},
    {"title": "现代操作系统", "author": "Andrew S. Tanenbaum", "isbn": "978-7-115-xxxxx", "tag": "os,textbook"},
    {"title": "计算机网络：自顶向下方法", "author": "James F. Kurose", "isbn": "978-7-115-xxxxx", "tag": "network,textbook"},
    {"title": "数据库系统概念", "author": "Abraham Silberschatz", "isbn": "978-7-115-xxxxx", "tag": "database,textbook"},
    {"title": "黑客与画家", "author": "Paul Graham", "isbn": "978-7-115-xxxxx", "tag": "cs,essay"},
    {"title": "代码大全", "author": "Steve McConnell", "isbn": "978-7-115-xxxxx", "tag": "software,engineering"},
    {"title": "程序员修炼之道", "author": "Andrew Hunt", "isbn": "978-7-115-xxxxx", "tag": "software,practice"},
    {"title": "设计模式：可复用面向对象软件的基础", "author": "Erich Gamma", "isbn": "978-7-115-xxxxx", "tag": "design-pattern,oop"},
    {"title": "重构：改善既有代码的设计", "author": "Martin Fowler", "isbn": "978-7-115-xxxxx", "tag": "refactoring,software"},
    {"title": "人月神话", "author": "Frederick P. Brooks", "isbn": "978-7-115-xxxxx", "tag": "software,management"},
    {"title": "UNIX编程艺术", "author": "Eric S. Raymond", "isbn": "978-7-115-xxxxx", "tag": "unix,os"},
    {"title": "编程珠玑", "author": "Jon Bentley", "isbn": "978-7-115-xxxxx", "tag": "algorithm,practice"},
    {"title": "TCP/IP详解", "author": "W. Richard Stevens", "isbn": "978-7-115-xxxxx", "tag": "network,tcpip"},
    {"title": "C程序设计语言 (K&R)", "author": "Brian W. Kernighan", "isbn": "978-7-115-xxxxx", "tag": "c,programming"},
    {"title": "C++ Primer中文版", "author": "Stanley B. Lippman", "isbn": "978-7-115-xxxxx", "tag": "cpp,textbook"},
    {"title": "Java编程思想", "author": "Bruce Eckel", "isbn": "978-7-115-xxxxx", "tag": "java,textbook"},
    {"title": "Python编程：从入门到实践", "author": "Eric Matthes", "isbn": "978-7-115-xxxxx", "tag": "python,tutorial"},
    {"title": "机器学习 (西瓜书)", "author": "周志华", "isbn": "978-7-115-xxxxx", "tag": "ml,textbook"},
    {"title": "统计学习方法", "author": "李航", "isbn": "978-7-115-xxxxx", "tag": "ml,statistics"},
    {"title": "深度学习 (花书)", "author": "Ian Goodfellow", "isbn": "978-7-115-xxxxx", "tag": "dl,textbook"},
    {"title": "模式分类", "author": "Richard O. Duda", "isbn": "978-7-115-xxxxx", "tag": "pattern-recognition,textbook"},
    {"title": "数据挖掘：概念与技术", "author": "Jiawei Han", "isbn": "978-7-115-xxxxx", "tag": "datamining,textbook"},
    {"title": "人工智能：一种现代方法", "author": "Stuart Russell", "isbn": "978-7-115-xxxxx", "tag": "ai,textbook"},
    # === 数学 ===
    {"title": "具体数学", "author": "Ronald L. Graham", "isbn": "978-7-115-xxxxx", "tag": "math,cs"},
    {"title": "概率论与数理统计", "author": "William Feller", "isbn": "978-7-115-xxxxx", "tag": "math,statistics"},
    {"title": "线性代数及其应用", "author": "David C. Lay", "isbn": "978-7-115-xxxxx", "tag": "math,linear-algebra"},
    {"title": "微积分学教程", "author": "Г.М.菲赫金哥尔茨", "isbn": "978-7-115-xxxxx", "tag": "math,calculus"},
    {"title": "实变函数论", "author": "那汤松", "isbn": "978-7-115-xxxxx", "tag": "math,analysis"},
    {"title": "复变函数", "author": "阿尔福斯", "isbn": "978-7-115-xxxxx", "tag": "math,complex-analysis"},
    {"title": "组合数学", "author": "Richard A. Brualdi", "isbn": "978-7-115-xxxxx", "tag": "math,combinatorics"},
    {"title": "图论导引", "author": "Douglas B. West", "isbn": "978-7-115-xxxxx", "tag": "math,graph-theory"},
    {"title": "数论导引", "author": "G. H. Hardy", "isbn": "978-7-115-xxxxx", "tag": "math,number-theory"},
]

def _safe_id(title):
    return hashlib.md5(title.encode()).hexdigest()[:12]

def _safe_name(title):
    return re.sub(r'[\\\\/:*?\"<>|]', '_', title)[:80]

def store(store_type, category, title, content, source_url="", metadata=None):
    """存储一条采集记录"""
    target = DIRS.get(store_type, ROOT / store_type)
    item_id = _safe_id(title)
    safe_title = _safe_name(title)
    record = {
        "id": item_id,
        "type": store_type,
        "category": category,
        "title": title[:300],
        "content": (content or "")[:3000],
        "source": source_url,
        "metadata": metadata or {},
        "collected_at": datetime.now().isoformat(),
    }
    subdir = target / category.replace("/", "_")
    subdir.mkdir(parents=True, exist_ok=True)
    fpath = subdir / f"{item_id}_{safe_title}.json"
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    # 更新日志
    _log_collection(store_type, category, item_id, title[:60])
    return str(fpath)

def _log_collection(store_type, category, item_id, title_short):
    log = {}
    if COLLECT_LOG.exists():
        with open(COLLECT_LOG, "r") as f:
            log = json.load(f)
    if "collections" not in log:
        log["collections"] = []
    if "stats" not in log:
        log["stats"] = {}
    log["collections"].append({
        "id": item_id, "type": store_type, "category": category,
        "title": title_short, "ts": datetime.now().isoformat()
    })
    key = f"{store_type}/{category}"
    log["stats"][key] = log["stats"].get(key, 0) + 1
    log["last_run"] = datetime.now().isoformat()
    if len(log["collections"]) > 2000:
        log["collections"] = log["collections"][-1000:]
    with open(COLLECT_LOG, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

def store_turing_book(book):
    """存储图灵系列图书元数据"""
    item_id = _safe_id(book["title"])
    safe_title = _safe_name(book["title"])
    record = {
        **book,
        "id": item_id,
        "series": "图灵程序设计丛书",
        "collected_at": datetime.now().isoformat(),
    }
    fpath = DIRS["book_turing"] / f"{item_id}_{safe_title}.json"
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    _log_collection("book_turing", book.get("tag", "general"), item_id, book["title"][:60])
    return str(fpath)

def collect_turing_library():
    """采集图灵系列图书库（已有书目）"""
    results = []
    for book in TURING_BOOKS:
        path = store_turing_book(book)
        results.append(path)
    print(f"✅ 图灵系列: 已存储 {len(results)} 本书目元数据")
    return results

def search_and_collect(query, store_type, category, max_results=10):
    """使用web搜索+摘要采集"""
    try:
        from hermes_tools import web_search, web_extract
        # Web搜索
        search_result = web_search(query=query, limit=max_results)
        web_data = search_result.get("data", {}).get("web", [])
        if not web_data:
            print(f"  ⚠ 无搜索结果: {query}")
            return []
        # 提取URLs
        urls = [r.get("url", "") for r in web_data if r.get("url")]
        # 提取内容
        pages = web_extract(urls=urls[:3], char_limit=2000)
        results = []
        for i, r in enumerate(web_data[:max_results]):
            title = r.get("title", "")
            desc = r.get("description", "")
            url = r.get("url", "")
            content = desc
            if i < len(pages.get("results", [])):
                pg = pages["results"][i]
                if pg.get("content"):
                    content = pg["content"][:2000]
            path = store(store_type, category, title, content, url)
            results.append(path)
        print(f"  ✅ {store_type}/{category}: 采集 {len(results)} 条")
        return results
    except ImportError:
        print("  ⚠ hermes_tools不可用，尝试urllib方式")
        return _search_via_urllib(query, store_type, category, max_results)
    except Exception as e:
        print(f"  ❌ 搜索失败 {query}: {e}")
        return []

def _search_via_urllib(query, store_type, category, max_results=5):
    """Fallback: 用urllib搜索Bing"""
    import urllib.parse
    try:
        encoded = urllib.parse.quote(query)
        # Bing CN
        url = f"https://cn.bing.com/search?q={encoded}&count={max_results}"
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp = urlopen(req, context=SSL_CTX, timeout=15)
        html = resp.read().decode("utf-8", errors="replace")
        # 简易提取标题和链接
        results = []
        for m in re.finditer(r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', html):
            link, t = m.group(1), re.sub(r'<[^>]+>', "", m.group(2)).strip()
            if t and len(t) > 5 and len(results) < max_results:
                results.append({"title": t, "url": link, "description": ""})
        for r in results[:max_results]:
            store(store_type, category, r["title"], r["description"], r["url"])
        print(f"  ✅ {store_type}/{category}: urllib采集 {len(results)} 条")
        return [r["url"] for r in results]
    except Exception as e:
        print(f"  ❌ urllib搜索失败 {query}: {e}")
        return []

def stats():
    """采集统计"""
    log = {}
    if COLLECT_LOG.exists():
        with open(COLLECT_LOG) as f:
            log = json.load(f)
    s = log.get("stats", {})
    total = sum(s.values())
    print(f"\n📊 巡天知识采集统计:")
    print(f"   总计: {total} 条记录")
    for key in sorted(s.keys()):
        print(f"   {key}: {s[key]}条")
    # 目录文件数
    for name, d in DIRS.items():
        count = sum(len(files) for _, _, files in os.walk(d)) if d.exists() else 0
        print(f"   目录 {name}: {count} 文件")
    return {"total": total, "stats": s, "last_run": log.get("last_run")}

# ── 在线搜索采集入口 ──
def collect_textbooks():
    """采集CS/数学/物理教材"""
    queries = {
        "cs": "计算机科学经典教材 图灵系列",
        "math": "数学经典教材 高等数学 线性代数",
        "physics": "物理学经典教材 费曼物理学讲义",
        "engineering": "工程学经典教材 电路 信号与系统",
    }
    total = 0
    for cat, q in queries.items():
        results = search_and_collect(q, "textbook", cat, max_results=8)
        total += len(results)
        time.sleep(1)
    return total

def collect_literature():
    """采集文献/综述"""
    queries = {
        "papers": "AI machine learning survey paper 2024 2025",
        "reviews": "computer science review article recent advances",
        "theses": "PhD thesis machine learning systems",
    }
    total = 0
    for cat, q in queries.items():
        results = search_and_collect(q, "literature", cat, max_results=8)
        total += len(results)
        time.sleep(1)
    return total

def collect_reports():
    """采集行业/技术报告"""
    queries = {
        "tech": "technology trend report 2024 2025 AI",
        "industry": "industry report semiconductor EV battery",
        "research": "research report deep learning advances",
    }
    total = 0
    for cat, q in queries.items():
        results = search_and_collect(q, "report", cat, max_results=8)
        total += len(results)
        time.sleep(1)
    return total

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    
    if cmd == "init":
        for name, d in DIRS.items():
            d.mkdir(parents=True, exist_ok=True)
            for sub in ["cs", "math", "physics", "general"]:
                (d / sub).mkdir(parents=True, exist_ok=True)
        if not COLLECT_LOG.exists():
            with open(COLLECT_LOG, "w") as f:
                json.dump({"collections": [], "stats": {}, "last_run": None}, f)
        print("✅ 巡天知识采集 v4 初始化完成")
        print(f"   目标: 教材/文献/报告/图灵系列")
        print(f"   存储: {ROOT}")
        
    elif cmd == "turing":
        collect_turing_library()
        
    elif cmd == "textbooks":
        collect_textbooks()
        
    elif cmd == "literature":
        collect_literature()
        
    elif cmd == "reports":
        collect_reports()
        
    elif cmd == "all":
        print("🔍 巡天全量采集启动...\n")
        turing = collect_turing_library()
        print()
        tb = collect_textbooks()
        print()
        lit = collect_literature()
        print()
        rep = collect_reports()
        print()
        print(f"🎯 全量采集完成!")
        print(f"   图灵系列: {len(turing)} 条")
        print(f"   教材: {tb} 条")
        print(f"   文献: {lit} 条")
        print(f"   报告: {rep} 条")
        stats()
        
    elif cmd == "stats":
        stats()
        
    else:
        print(f"用法: python3 {sys.argv[0]} [init|turing|textbooks|literature|reports|all|stats]")
