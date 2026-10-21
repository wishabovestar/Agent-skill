#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第十五轮：Bing 搜 GitHub 具体仓库名"""
import subprocess, re, html, urllib.parse, time

def bing_search(query, limit=10):
    url = "https://cn.bing.com/search?q=" + urllib.parse.quote(query) + "&count=20"
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "20", "-A",
             "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
             "-H", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
             url],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        data = r.stdout
    except Exception as e:
        return {"error": str(e)}
    items = []
    blocks = re.findall(r'<li class="b_algo".*?</li>', data, re.S)
    for b in blocks[:limit]:
        m = re.search(r'<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
        if not m:
            continue
        url = m.group(1)
        title = re.sub(r'<[^>]+>', '', m.group(2))
        title = html.unescape(title).strip()
        desc_m = re.search(r'<p[^>]*>(.*?)</p>', b, re.S)
        desc = re.sub(r'<[^>]+>', '', desc_m.group(1)) if desc_m else ''
        desc = html.unescape(desc).strip()
        items.append({"title": title, "url": url, "desc": desc[:200]})
    return {"items": items}

if __name__ == "__main__":
    for q in ["github.com open source AI agent framework new 2026",
              "github 开源项目 AI 智能体 框架 2026年8月",
              "github trending LLM tool agent repo"]:
        res = bing_search(q)
        print(f"\n-- {q} --")
        for it in res.get("items", []):
            # 只输出 github.com 域名的
            if "github.com" in it["url"]:
                print(f"- {it['title']} | {it['url']}")
                if it['desc']:
                    print(f"  {it['desc'][:150]}")
        time.sleep(1.2)
