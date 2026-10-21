#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第四轮：深度抓取文章 + GitHub trending 具体项目 + arXiv 论文镜像"""
import subprocess, re, html, urllib.parse, time

def fetch(url, ua=None):
    try:
        r = subprocess.run(
            ["curl", "-sL", "--max-time", "30", "-A",
             ua or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
             "-H", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
             url],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40)
        return r.stdout
    except Exception as e:
        return f"ERR {e}"

def strip_html(data):
    data = re.sub(r'<script.*?</script>', ' ', data, flags=re.S)
    data = re.sub(r'<style.*?</style>', ' ', data, flags=re.S)
    data = re.sub(r'<[^>]+>', ' ', data)
    data = html.unescape(data)
    data = re.sub(r'[ \t]+', ' ', data)
    data = re.sub(r'\n\s*\n+', '\n', data)
    return data.strip()

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
        items.append({"title": title, "url": url, "desc": desc[:250]})
    return {"items": items}

if __name__ == "__main__":
    # 1. GitHub trending 具体项目
    print("########## GitHub Trending 搜索 ##########")
    for q in ["github trending today repositories", "github most starred this week 2026 August"]:
        res = bing_search(q)
        print(f"\n-- {q} --")
        for it in res.get("items", []):
            print(f"- {it['title']} | {it['url']}")
        time.sleep(1.2)

    # 2. arXiv 镜像/论文搜索
    print("\n\n########## arXiv 论文搜索 ##########")
    for q in [
        "arxiv 2408. transformer large language model new paper",
        "arxiv August 2026 diffusion model paper",
        "arxiv 2026 solid state battery paper",
        "site:arxiv.org August 2026",
    ]:
        res = bing_search(q)
        print(f"\n-- {q} --")
        for it in res.get("items", []):
            print(f"- {it['title']} | {it['url']}")
            if it["desc"]:
                print(f"  {it['desc'][:130]}")
        time.sleep(1.2)

    # 3. 病毒学最新
    print("\n\n########## 病毒学 ##########")
    for q in ["BA.3.2 Cicada COVID variant CDC", "WHO COVID-19 August 2026 update XFG"]:
        res = bing_search(q)
        print(f"\n-- {q} --")
        for it in res.get("items", []):
            print(f"- {it['title']} | {it['url']}")
            if it["desc"]:
                print(f"  {it['desc'][:130]}")
        time.sleep(1.2)
