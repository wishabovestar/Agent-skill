#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第十三轮：GitHub 第三方榜单博客 + AI 新闻细节 + 财经"""
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

def strip_tags(s):
    s = re.sub(r'<script.*?</script>', ' ', s, flags=re.S)
    s = re.sub(r'<style.*?</style>', ' ', s, flags=re.S)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = html.unescape(s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

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
    print("########## GitHub 第三方榜单博客 ##########")
    for q in ['"github trending" 2026年8月',
              '"most starred" OR "trending repos" August 2026 github']:
        res = bing_search(q)
        print(f"\n-- {q} --")
        for it in res.get("items", []):
            print(f"- {it['title']} | {it['url']}")
            if it['desc']:
                print(f"  {it['desc'][:150]}")
        time.sleep(1.2)

    print("\n########## AI 新闻细节 ##########")
    for q in ["DeepSeek V4 Pro agent 上线",
              "OpenAI GPT-5.6 release August 2026",
              "Kimi K3 网络安全测试"]:
        res = bing_search(q)
        print(f"\n-- {q} --")
        for it in res.get("items", []):
            print(f"- {it['title']} | {it['url']}")
            if it['desc']:
                print(f"  {it['desc'][:160]}")
        time.sleep(1.2)

    print("\n########## 财经新闻 ##########")
    for q in ["存储芯片 光通信 领涨 美股 CPI",
              "黄仁勋 5000亿美元 AI融资平台"]:
        res = bing_search(q)
        print(f"\n-- {q} --")
        for it in res.get("items", []):
            print(f"- {it['title']} | {it['url']}")
            if it['desc']:
                print(f"  {it['desc'][:160]}")
        time.sleep(1.2)
