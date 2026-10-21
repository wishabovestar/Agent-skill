#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三轮：定向抓取行业站点 + GitHub Trending 镜像 + 澎湃"""
import subprocess, re, html, time

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

def strip_html(data, keep_links=False):
    data = re.sub(r'<script.*?</script>', ' ', data, flags=re.S)
    data = re.sub(r'<style.*?</style>', ' ', data, flags=re.S)
    if keep_links:
        data = re.sub(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r'[\2](\1)', data, flags=re.S)
    data = re.sub(r'<[^>]+>', ' ', data)
    data = html.unescape(data)
    data = re.sub(r'[ \t]+', ' ', data)
    data = re.sub(r'\n\s*\n+', '\n', data)
    return data.strip()

if __name__ == "__main__":
    targets = [
        ("锂电网首页", "http://li-b.cn/", "utf-8"),
        ("北极星锂电池", "https://news.bjx.com.cn/topics/lidianchi/", "utf-8"),
        ("澎湃科技频道", "https://www.thepaper.cn/", "utf-8"),
        ("imfounder AI", "https://imfounder.com/science-tech/ai/ai-updates-august-2026-openai-astra-deepmind/", "utf-8"),
    ]
    for name, u, enc in targets:
        data = fetch(u)
        if data.startswith("ERR"):
            print(f"\n===== {name}: {data} =====")
            continue
        txt = strip_html(data)
        print(f"\n===== {name} ({u}) len={len(txt)} =====")
        print(txt[:1800])
        time.sleep(1.0)
