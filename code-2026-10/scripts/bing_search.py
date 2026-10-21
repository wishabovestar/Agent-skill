#!/usr/bin/env python3
"""
Bing CN Search Fallback — 当 web_search (DDGS) 超时时的替代搜索
用法: python bing_search.py "查询词"
"""
import sys, json, urllib.request, urllib.parse, re

def bing_search(query, count=8):
    url = f"https://cn.bing.com/search?q={urllib.parse.quote(query)}&count={count}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"error": str(e), "query": query}

    results = []
    blocks = re.findall(r'<li class="b_algo"[^>]*>(.*?)</li>', html, re.DOTALL)
    for block in blocks[:count]:
        url_match = re.search(r'href="(https?://[^"]+)"', block)
        title_match = re.search(r'<h2>.*?<a[^>]*>(.*?)</a>', block, re.DOTALL)
        snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
        if url_match:
            title = ""
            if title_match:
                title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
            snippet = ""
            if snippet_match:
                snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip()
                snippet = re.sub(r'\s+', ' ', snippet)[:250]
            url = url_match.group(1)
            if not url.startswith("https://r.bing.com"):
                results.append({
                    "url": url,
                    "title": title or url,
                    "description": snippet
                })

    return {"web": results, "query": query, "count": len(results)}

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "test"
    result = bing_search(query)
    print(json.dumps(result, ensure_ascii=False, indent=2))
