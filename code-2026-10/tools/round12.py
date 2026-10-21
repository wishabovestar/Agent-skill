#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第十二轮：tophub 今日热榜 GitHub + 澎湃 DeepSeek 详情 + AI 聚合"""
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

def strip_tags(s):
    s = re.sub(r'<script.*?</script>', ' ', s, flags=re.S)
    s = re.sub(r'<style.*?</style>', ' ', s, flags=re.S)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = html.unescape(s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

if __name__ == "__main__":
    # tophub 热榜首页
    print("########## tophub.today ##########")
    data = fetch("https://tophub.today/")
    txt = strip_tags(data)
    print(f"len={len(txt)}")
    print(txt[:800])

    print("\n########## tophub GitHub 板块 ##########")
    # 找 github 相关的链接
    data2 = fetch("https://tophub.today/n/KqndgxeLl9")  # GitHub热榜
    if not data2.startswith("ERR") and data2.strip():
        txt2 = strip_tags(data2)
        print(f"len={len(txt2)}")
        print(txt2[:1200])
    else:
        print("ERR/EMPTY")

    print("\n########## 澎湃 DeepSeek V4 Pro 详情 ##########")
    # 澎湃新闻搜索
    data3 = fetch("https://www.thepaper.cn/searchResult.jsp?searchword=DeepSeek%20V4%20Pro")
    txt3 = strip_tags(data3)
    print(f"len={len(txt3)}")
    print(txt3[:800])
