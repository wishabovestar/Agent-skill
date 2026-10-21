#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bing CN 批量搜索抓取 (清除代理直连)"""
import subprocess, re, html, urllib.parse, time, json, sys

def bing_search(query, limit=8):
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
    # 提取结果块
    items = []
    # bing 结果: <li class="b_algo">...</li>
    blocks = re.findall(r'<li class="b_algo".*?</li>', data, re.S)
    if not blocks:
        blocks = re.findall(r'<li class="b_algo".*?</h2>.*?</li>', data, re.S)
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
        items.append({"title": title, "url": url, "desc": desc[:300]})
    return {"items": items, "raw_len": len(data)}

if __name__ == "__main__":
    queries = [
        "COVID-19 variant August 2026 WHO",
        "influenza flu CDC update August 2026",
        "AI model release news August 2026",
        "GitHub trending repositories",
        "碳酸锂价格 最新 2026年8月",
        "固态电池 最新进展 2026",
        "semiconductor earnings Nvidia TSMC August 2026",
        "科技 财报 半导体 2026年8月",
    ]
    out = {}
    for q in queries:
        res = bing_search(q)
        out[q] = res
        print(f"\n===== {q} =====")
        if "error" in res:
            print("ERR:", res["error"])
        else:
            for it in res["items"]:
                print(f"- {it['title']} | {it['url']}")
                if it["desc"]:
                    print(f"  {it['desc'][:150]}")
        time.sleep(1.5)
