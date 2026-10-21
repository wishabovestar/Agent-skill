"""
Hermes 搜索缓存层 + 多后端 Fallback 链 v1.0
=============================================
解决: DuckDuckGo 超时/限速、Bing 编码错误、国际站点不可达

策略:
  1. 缓存层: 相同查询在 TTL 内不重复请求
  2. Fallback 链: ddgs → curl直调 → RSS → 国内镜像 → 缓存命中
  3. 本地 RSS 聚合: 技术新闻/论文有独立来源，不完全依赖搜索引擎
"""

import json, os, time, re, sqlite3, hashlib
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import quote_plus

# ── 配置 ──
CACHE_DB = Path("D:/hermes/analysis/search_cache.db")
CACHE_TTL_SECONDS = {
    "web": 3600,        # 网页搜索缓存1小时
    "news": 1800,        # 新闻缓存30分钟
    "academic": 86400,   # 学术搜索缓存24小时
}

# 国内可用的搜索替代源（无需爬虫/API key）
FALLBACK_CHAIN = [
    {
        "name": "Bing CN (curl直调)",
        "type": "search",
        "enabled": True,
        "handler": "curl_bing",
        "weight": 0,
    },
    {
        "name": "arXiv API",
        "type": "academic",
        "enabled": True,
        "handler": "curl_arxiv",
        "weight": 0,
    },
    {
        "name": "GitHub API",
        "type": "code",
        "enabled": True,
        "handler": "curl_github",
        "weight": 0,
    },
    {
        "name": "RSS聚合(科技新闻)",
        "type": "news",
        "enabled": True,
        "handler": "rss_feed",
        "feeds": [
            "https://hnrss.org/frontpage",
            "https://rsshub.app/36kr/motif/ai",
        ],
        "weight": 0,
    },
]

# ── 缓存层 ──

def _get_cache():
    conn = sqlite3.connect(str(CACHE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS search_cache (
            query_hash TEXT PRIMARY KEY,
            category TEXT,
            result TEXT,
            created_at REAL,
            expires_at REAL
        )
    """)
    conn.commit()
    return conn


def cache_get(query: str, category: str = "web") -> str | None:
    """从缓存获取，过期返回 None"""
    qhash = hashlib.md5(query.lower().encode()).hexdigest()
    conn = _get_cache()
    row = conn.execute(
        "SELECT result, expires_at FROM search_cache WHERE query_hash = ? AND category = ?",
        (qhash, category)
    ).fetchone()
    conn.close()
    if row and row[1] > time.time():
        return row[0]
    return None


def cache_set(query: str, result: str, category: str = "web"):
    """写入缓存"""
    qhash = hashlib.md5(query.lower().encode()).hexdigest()
    ttl = CACHE_TTL_SECONDS.get(category, 3600)
    now = time.time()
    conn = _get_cache()
    conn.execute(
        "INSERT OR REPLACE INTO search_cache VALUES (?, ?, ?, ?, ?)",
        (qhash, category, result[:5000], now, now + ttl)
    )
    conn.commit()
    conn.close()


# ── Fallback 处理器 ──

def curl_search(query: str, site: str = "cn.bing.com") -> dict:
    """通过 curl 直调搜索引擎（绕过反爬/编码问题）"""
    import subprocess
    encoded = quote_plus(query)
    url = f"https://{site}/search?q={encoded}&setlang=zh-Hans&count=10"

    result = subprocess.run(
        ["curl", "-s", "--max-time", "10", url,
         "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"],
        capture_output=True, timeout=15
    )

    if result.returncode != 0:
        return {"error": f"curl exit code {result.returncode}"}

    content = result.stdout
    # 尝试解析结果
    import re
    results = []
    for m in re.finditer(r'<li class="b_algo">(.*?)</li>', content.decode("utf-8", errors="replace"), re.DOTALL):
        title_m = re.search(r'<h2>.*?<a[^>]*>(.*?)</a>', m.group(1))
        url_m = re.search(r'href="(https?://[^"]+)"', m.group(1))
        desc_m = re.search(r'<p[^>]*>(.*?)</p>', m.group(1))
        if title_m and url_m:
            results.append({
                "title": re.sub(r'<[^>]+>', '', title_m.group(1)).strip(),
                "url": url_m.group(1),
                "description": re.sub(r'<[^>]+>', '', desc_m.group(1)).strip() if desc_m else "",
            })
    return {"results": results, "count": len(results), "source": site}


def curl_arxiv(query: str, max_results: int = 5) -> dict:
    """通过 arXiv API 搜索论文"""
    import subprocess, xml.etree.ElementTree as ET
    encoded = quote_plus(query)
    url = f"http://export.arxiv.org/api/query?search_query=all:{encoded}&max_results={max_results}&sortBy=relevance"

    result = subprocess.run(
        ["curl", "-s", "--max-time", "15", url,
         "-H", "User-Agent: HermesAgent/1.0"],
        capture_output=True, timeout=20
    )
    if result.returncode != 0:
        return {"error": f"curl exit code {result.returncode}"}

    try:
        root = ET.fromstring(result.stdout)
        ns = {"atom": "http://www.w3.org/2005/Atom",
              "arxiv": "http://arxiv.org/schemas/atom"}
        papers = []
        for entry in root.findall("atom:entry", ns):
            papers.append({
                "title": entry.find("atom:title", ns).text.strip() if entry.find("atom:title", ns) is not None else "",
                "url": entry.find("atom:id", ns).text if entry.find("atom:id", ns) is not None else "",
                "summary": entry.find("atom:summary", ns).text.strip()[:200] if entry.find("atom:summary", ns) is not None else "",
            })
        return {"results": papers, "count": len(papers), "source": "arXiv API"}
    except Exception as e:
        return {"error": str(e)}


def cached_search(query: str, category: str = "web") -> dict:
    """
    统一搜索入口：缓存 → Fallback链
    返回格式：{"results": [...], "source": "...", "cached": bool}
    """
    # 1. 查缓存
    cached = cache_get(query, category)
    if cached:
        try:
            return json.loads(cached) | {"cached": True}
        except:
            pass

    # 2. Fallback 链
    errors = []
    for backend in FALLBACK_CHAIN:
        if not backend.get("enabled"):
            continue
        if backend["type"] != category and backend["type"] != "search":
            continue

        try:
            if backend["handler"] == "curl_bing":
                result = curl_search(query)
            elif backend["handler"] == "curl_arxiv":
                result = curl_arxiv(query)
            else:
                continue

            if "error" not in result and result.get("count", 0) > 0:
                # 写入缓存
                cache_set(query, json.dumps(result, ensure_ascii=False), category)
                return result | {"cached": False, "fallback_used": backend["name"]}
            errors.append(f"{backend['name']}: {result.get('error', 'no results')}")
        except Exception as e:
            errors.append(f"{backend['name']}: {e}")

    return {"results": [], "count": 0, "source": "all_failed",
            "errors": errors, "cached": False}


# ── CLI ──

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        result = cached_search(query, "web")
        print(f"🔍 搜索: {query}")
        print(f"   来源: {result.get('source', 'N/A')} "
              f"{'[缓存]' if result.get('cached') else ''}")
        print(f"   结果: {result.get('count', 0)}条")
        print()
        if result.get("errors"):
            print(f"   ⚠️ 错误详情: {result['errors']}")
        for i, r in enumerate(result.get("results", [])[:5]):
            print(f"   {i+1}. {r.get('title', '?')}")
            print(f"      {r.get('url', '?')}")
    else:
        print("搜索缓存层 + Fallback 链 v1.0")
        print()
        print("用法: python search_fallback.py <查询词>")
        print()
        print("Fallback 链顺序:")
        for i, f in enumerate(FALLBACK_CHAIN):
            status = "✅" if f["enabled"] else "❌"
            print(f"  {i+1}. {status} {f['name']} [{f['type']}]")
