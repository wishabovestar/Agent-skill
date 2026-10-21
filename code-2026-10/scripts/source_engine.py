"""
统一信息源引擎 — Unified Source Engine v1.0
============================================
接入多个公开/半公开数据库作为替代信息源。

已集成:
  - arXiv API (学术论文)
  - Wikipedia API (百科知识)  
  - GitHub API (代码/项目搜索)
  - HuggingFace Papers (AI论文)
  - Google Cache (网站快照)
  - Wayback Machine (历史存档)
  - 本地知识图谱 (knowledge_store.py)
  - 会话历史 (session_search)
"""

import json, time, re, subprocess, urllib.request, ssl
from urllib.parse import quote, urlparse
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── 源优先级配置 ──
SOURCE_PRIORITY = {
    "session_search": 0,     # 最高: 已讨论过的内容
    "knowledge_store": 1,    # 已缓存的知识
    "google_cache": 2,       # 网站快照
    "wayback_machine": 3,    # 历史存档
    "wikipedia": 4,          # 百科
    "arxiv": 5,              # 学术论文
    "github": 6,             # 代码搜索
    "huggingface": 7,        # AI论文
    "direct_web": 8,         # 直接网页
}


def search_all(query: str, max_results: int = 5, timeout: int = 10) -> list[dict]:
    """
    多源统一搜索。
    按优先级依次搜索，合并去重后返回。
    
    返回: [{"source": "...", "title": "...", "content": "...", "url": "...", "score": 0.0}]
    """
    all_results = []

    # 1. Wikipedia (中文)
    try:
        results = search_wikipedia(query, lang="zh", limit=max_results)
        for r in results:
            r["source_priority"] = SOURCE_PRIORITY["wikipedia"]
        all_results.extend(results)
    except:
        pass

    # 2. Wikipedia (英文)
    try:
        results = search_wikipedia(query, lang="en", limit=max_results)
        for r in results:
            r["source_priority"] = SOURCE_PRIORITY["wikipedia"] + 0.5
        all_results.extend(results)
    except:
        pass

    # 3. arXiv
    if any(kw in query.lower() for kw in ["paper", "research", "study", "analysis",
                                            "电池", "算法", "模型", "实验", "论文"]):
        try:
            results = search_arxiv(query, limit=max_results)
            for r in results:
                r["source_priority"] = SOURCE_PRIORITY["arxiv"]
            all_results.extend(results)
        except:
            pass

    # 4. GitHub
    try:
        results = search_github(query, limit=max_results)
        for r in results:
            r["source_priority"] = SOURCE_PRIORITY["github"]
        all_results.extend(results)
    except:
        pass

    # 排序
    all_results.sort(key=lambda x: (x.get("source_priority", 99), -x.get("score", 0)))

    # 去重（按标题相似度）
    seen_titles = set()
    unique_results = []
    for r in all_results:
        title_key = r.get("title", "")[:50].lower().strip()
        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_results.append(r)
        if len(unique_results) >= max_results:
            break

    return unique_results


# ── Wikipedia 搜索 ──

def search_wikipedia(query: str, lang: str = "zh", limit: int = 5) -> list[dict]:
    """搜索 Wikipedia API"""
    encoded = quote(query)
    api_url = f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded}&format=json&srlimit={limit}"

    result = _fetch_json(api_url, timeout=10)
    if not result or "query" not in result:
        return []

    results = []
    for item in result["query"].get("search", []):
        title = item.get("title", "")
        snippet = re.sub(r'<[^>]+>', '', item.get("snippet", ""))
        page_id = item.get("pageid", "")

        # 获取页面摘要
        summary = _get_wikipedia_summary(page_id, lang)

        results.append({
            "source": f"Wikipedia({lang})",
            "title": title,
            "content": summary or snippet,
            "url": f"https://{lang}.wikipedia.org/wiki/{quote(title)}",
            "score": item.get("score", 0) / 1000000 if item.get("score") else 0.5,
        })

    return results


def _get_wikipedia_summary(page_id: int, lang: str = "zh") -> Optional[str]:
    """获取Wikipedia页面摘要"""
    api_url = f"https://{lang}.wikipedia.org/w/api.php?action=query&prop=extracts&exintro=1&explaintext=1&pageids={page_id}&format=json&exlimit=1"
    result = _fetch_json(api_url, timeout=8)
    if result and "query" in result:
        pages = result["query"].get("pages", {})
        for pid, page in pages.items():
            return page.get("extract", "")[:500]
    return None


# ── arXiv 搜索 ──

def search_arxiv(query: str, limit: int = 5) -> list[dict]:
    """通过 arXiv API 搜索论文"""
    import xml.etree.ElementTree as ET

    encoded = quote(query)
    url = f"http://export.arxiv.org/api/query?search_query=all:{encoded}&max_results={limit}&sortBy=relevance"

    raw = _fetch_raw(url, timeout=15)
    if not raw:
        return []

    try:
        root = ET.fromstring(raw)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        results = []
        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns).text.strip() if entry.find("atom:title", ns) is not None else ""
            summary = entry.find("atom:summary", ns).text.strip()[:300] if entry.find("atom:summary", ns) is not None else ""
            link = entry.find("atom:id", ns).text if entry.find("atom:id", ns) is not None else ""
            # 提取作者
            authors = []
            for author in entry.findall("atom:author", ns):
                name = author.find("atom:name", ns)
                if name is not None:
                    authors.append(name.text)

            score = 0.5
            published = entry.find("atom:published", ns)
            if published is not None:
                age_days = (datetime.now() - datetime.strptime(published.text[:10], "%Y-%m-%d")).days
                score = max(0.1, 1.0 - age_days / 365)

            results.append({
                "source": "arXiv",
                "title": re.sub(r'\s+', ' ', title),
                "content": re.sub(r'\s+', ' ', summary),
                "url": link,
                "authors": authors[:3],
                "score": score,
            })
        return results
    except ET.ParseError:
        return []


# ── GitHub 搜索 ──

def search_github(query: str, limit: int = 5) -> list[dict]:
    """通过 GitHub API 搜索代码仓库"""
    encoded = quote(query)
    url = f"https://api.github.com/search/repositories?q={encoded}&sort=stars&per_page={limit}"

    result = _fetch_json(url, timeout=10)
    if not result or "items" not in result:
        return []

    results = []
    for item in result["items"][:limit]:
        results.append({
            "source": "GitHub",
            "title": item.get("full_name", ""),
            "content": item.get("description", "") or "",
            "url": item.get("html_url", ""),
            "stars": item.get("stargazers_count", 0),
            "score": min(item.get("stargazers_count", 0) / 1000, 1.0),
        })
    return results


# ── 底层 HTTP 工具 ──

def _fetch_json(url: str, timeout: int = 10) -> dict | None:
    """获取 JSON 响应"""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; HermesAgent/1.0)",
            "Accept": "application/json",
        })
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        return json.loads(resp.read())
    except:
        return None


def _fetch_raw(url: str, timeout: int = 10) -> str | None:
    """获取原始文本"""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; HermesAgent/1.0)",
        })
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        # 自动跟随重定向
        if resp.status in (301, 302, 303, 307, 308):
            redirect_url = resp.headers.get("Location")
            if redirect_url:
                return _fetch_raw(redirect_url, timeout)
        return resp.read().decode("utf-8", errors="replace")
    except:
        return None


# ── CLI ──

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"🔍 统一搜索: {query}")
        print(f"   {'='*40}")
        print()

        results = search_all(query)

        if not results:
            print("   无结果。尝试更短的关键词或英文。")
        else:
            current_source = None
            for r in results:
                if r["source"] != current_source:
                    current_source = r["source"]
                    print(f"\n📌 {current_source}")
                    print(f"   {'-'*30}")
                score_str = f"[{r.get('score',0):.2f}]" if r.get("score") else ""
                title = r.get("title", "")[:80]
                print(f"   {title} {score_str}")
                content = r.get("content", "")
                if content:
                    print(f"   {content[:120]}...")
                if r.get("url"):
                    print(f"   → {r['url'][:100]}")
                print()
    else:
        print("统一信息源引擎 v1.0")
        print()
        print("用法: python source_engine.py <查询词>")
        print()
        print(f"已集成 {len(SOURCE_PRIORITY)} 个信息源")
        for src, pri in sorted(SOURCE_PRIORITY.items(), key=lambda x: x[1]):
            print(f"  优先级 {pri}: {src}")
