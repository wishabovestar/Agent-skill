#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第二轮：精确查询 + 抓取关键聚合页"""
import subprocess, re, html, urllib.parse, time, json

def fetch(url):
    try:
        r = subprocess.run(
            ["curl", "-sL", "--max-time", "25", "-A",
             "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
             "-H", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
             url],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=35)
        return r.stdout
    except Exception as e:
        return f"ERR {e}"

def strip_html(data):
    data = re.sub(r'<script.*?</script>', ' ', data, flags=re.S)
    data = re.sub(r'<style.*?</style>', ' ', data, flags=re.S)
    data = re.sub(r'<[^>]+>', ' ', data)
    data = html.unescape(data)
    data = re.sub(r'\s+', ' ', data)
    return data.strip()

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
        items.append({"title": title, "url": url, "desc": desc[:300]})
    return {"items": items}

if __name__ == "__main__":
    queries = [
        '"solid state battery" news August 2026',
        '"lithium battery" breakthrough August 2026',
        '固态电池 半固态 量产 2026年8月',
        '碳酸锂期货 8月 价格 走势',
        'AI芯片 财报 Nvidia 2026年8月',
        'arxiv paper transformer diffusion August 2026',
        'Google Gemini OpenAI Claude August 2026 release',
    ]
    for q in queries:
        res = bing_search(q)
        print(f"\n===== {q} =====")
        if "error" in res:
            print("ERR:", res["error"])
        else:
            for it in res["items"]:
                print(f"- {it['title']} | {it['url']}")
                if it["desc"]:
                    print(f"  {it['desc'][:160]}")
        time.sleep(1.2)

    print("\n\n########## 聚合页抓取 ##########")
    pages = {
        "AI mega update": "https://www.aiapps.com/blog/august-2026-ai-mega-update-major-breakthroughs-launches/",
        "AI updates imfounder": "https://imfounder.com/science-tech/ai/ai-updates-august-2026-openai-astra-deepmind/",
        "LLM gateway timeline": "https://llmgateway.io/timeline",
        "benchlm releases": "https://benchlm.ai/model-updates/releases/august-2026",
    }
    for name, u in pages.items():
        data = fetch(u)
        txt = strip_html(data)
        print(f"\n===== PAGE: {name} ({u}) =====")
        print(txt[:1200])
        time.sleep(1.0)
