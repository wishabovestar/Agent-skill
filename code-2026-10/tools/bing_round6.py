#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第六轮：GitHub trending 第三方聚合 + arXiv 论文标题搜索 + 澎湃科技"""
import subprocess, re, html, urllib.parse, time, json

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
    print("########## GitHub 聚合站 ##########")
    for u in ["https://ossinsight.io/collections/trending-repos/",
              "https://github-trending-api.now.sh/repositories",
              "https://api.gitterapp.com/repositories"]:
        data = fetch(u)
        if data.startswith("ERR") or not data.strip():
            print(f"== {u}: EMPTY/ERR")
            continue
        try:
            j = json.loads(data)
            print(f"== {u}: JSON {type(j)}")
            items = j if isinstance(j, list) else j.get('data', j.get('repositories', []))
            for r in (items or [])[:10]:
                if isinstance(r, dict):
                    print(f"  {r.get('fullName') or r.get('full_name') or r.get('name')} ★{r.get('stars') or r.get('stargazers_count')} | {(r.get('description') or '')[:90]}")
        except Exception as e:
            txt = strip_html(data)
            print(f"== {u}: len={len(txt)} err={e}")
            print(txt[:500])
        time.sleep(1.0)

    print("\n########## arXiv 论文标题搜索 ##########")
    for q in [
        '"arxiv.org/abs" transformer August 2026',
        '"arxiv.org/abs" diffusion model 2026',
        'arxiv 最新论文 深度学习 2026年8月',
    ]:
        res = bing_search(q)
        print(f"\n-- {q} --")
        for it in res.get("items", []):
            print(f"- {it['title']} | {it['url']}")
            if it["desc"]:
                print(f"  {it['desc'][:140]}")
        time.sleep(1.2)

    print("\n########## 澎湃科技新闻 ##########")
    data = fetch("https://www.thepaper.cn/channel_25951")  # 科技频道
    txt = strip_html(data)
    print(f"len={len(txt)}")
    print(txt[:1200])
