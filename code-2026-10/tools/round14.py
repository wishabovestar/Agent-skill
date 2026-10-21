#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第十四轮：GitHub 端点全面测试 + 病毒学/锂电补充"""
import subprocess, re, html, time

def fetch(url, ua=None):
    try:
        r = subprocess.run(
            ["curl", "-sL", "--max-time", "25", "-A",
             ua or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
             "-H", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
             url],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=35)
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

if __name__ == "__main__":
    print("########## GitHub 端点测试 ##########")
    for u in [
        "http://github.com/trending",
        "https://github.com/trending/developers",
        "https://api.github.com/zen",
        "https://codeload.github.com",
        "https://github.com/trending?since=weekly",
        "https://ghp.ci/https://raw.githubusercontent.com",
        "https://ghproxy.net/https://raw.githubusercontent.com/trending",
    ]:
        data = fetch(u)
        if data.startswith("ERR"):
            print(f"== {u}: ERR {data[:40]}")
        elif not data.strip():
            print(f"== {u}: EMPTY")
        else:
            print(f"== {u}: len={len(data)}")
            print(strip_tags(data)[:300])
        time.sleep(0.6)

    # 病毒学：中国CDC 新冠月报
    print("\n########## 中国CDC新冠月报 ##########")
    data = fetch("https://www.chinacdc.cn/jksj/xgbdyq/")
    txt = strip_tags(data)
    print(f"len={len(txt)}")
    # 提取相关标题
    for m in re.finditer(r'(20\d{2}年\d{1,2}月|疫情情况|流感样病例|发热门诊)[^。]{0,80}', txt):
        print("-", m.group(0)[:100])
    print(txt[:600])
