"""
Bing search for xuntian knowledge collection
Extracts clean search results from Bing CN (direct, no proxy)
"""
import re, json, html, urllib.request, sys
from urllib.parse import quote

def bing_search(query, max_results=8):
    url = f"https://cn.bing.com/search?q={quote(query)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=25)
        content = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"error": str(e), "query": query}

    # Extract results
    results = []
    # Pattern: <h2><a href="..." ...>title</a></h2>
    pattern1 = re.findall(
        r'<h2[^>]*><a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a></h2>',
        content, re.DOTALL
    )
    seen_urls = set()
    for url, title in pattern1:
        clean_title = re.sub(r'<[^>]+>', '', title)
        clean_title = html.unescape(clean_title).strip()
        # Clean Bing redirect URLs
        if "&url=" in url:
            url = re.search(r'[?&]url=([^&]+)', url)
            if url:
                url = urllib.parse.unquote(url.group(1))
            else:
                continue
        # Deduplicate
        url_key = url[:80]
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)
        if clean_title and len(clean_title) > 5:
            # Get description
            desc_pattern = re.search(
                r'<p[^>]*class="b_lineclamp2"[^>]*>(.*?)</p>',
                content[content.find(clean_title[:30]):content.find(clean_title[:30])+3000], re.DOTALL
            )
            desc = ""
            if desc_pattern:
                desc = re.sub(r'<[^>]+>', '', desc_pattern.group(1))
                desc = html.unescape(desc).strip()[:200]
            results.append({
                "title": clean_title,
                "url": url,
                "description": desc
            })
    return {"results": results[:max_results], "query": query, "count": len(results)}


def search_all(queries):
    """Run multiple searches and collect unique results"""
    all_results = {}
    for q in queries:
        print(f"\n{'='*60}")
        print(f"Q: {q[:80]}")
        print(f"{'='*60}")
        result = bing_search(q)
        if "error" in result:
            print(f"  ERROR: {result['error'][:80]}")
            all_results[q] = []
        else:
            print(f"  Found {result['count']} results")
            for i, r in enumerate(result["results"], 1):
                print(f"  {i}. {r['title'][:80]}")
                print(f"     {r['url'][:100]}")
            all_results[q] = result["results"]
    return all_results


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        result = bing_search(query)
        if "error" in result:
            print(f"ERROR: {result['error']}")
        else:
            for i, r in enumerate(result["results"], 1):
                print(f"{i}. {r['title']}")
                print(f"   {r['url']}")
                if r.get("description"):
                    print(f"   {r['description'][:120]}")
                print()
    else:
        # Run all P0 searches
        queries = [
            # P0: 预锂化综述
            "pre-lithiation review 2024 2025 lithium battery",
            "预锂化 综述 补锂 技术 2025",
            # P0: 预锂化论文
            "prelithiation silicon anode cathode additive 2024 2025",
            "Li5FeO4 prelithiation cathode material",
            # P0: 券商研报
            "预锂化 研报 电池 补锂",
            "电池科技前瞻 预锂化 报告",
            # P0: 教材
            "lithium battery textbook electrochemistry",
            "lithium-ion battery manufacturing textbook",
            # P0: 行业报告
            "锂电池行业报告 2025 预锂化",
            "battery pre-lithiation industry report 2025",
            # P1: 硅负极
            "silicon anode prelithiation review 2024 2025",
            "硅负极 预锂化 研究进展",
        ]
        search_all(queries)
