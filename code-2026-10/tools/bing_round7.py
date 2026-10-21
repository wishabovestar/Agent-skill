#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第七轮：澎湃文章详情 + arXiv 镜像测试"""
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

def strip_html(data):
    data = re.sub(r'<script.*?</script>', ' ', data, flags=re.S)
    data = re.sub(r'<style.*?</style>', ' ', data, flags=re.S)
    data = re.sub(r'<[^>]+>', ' ', data)
    data = html.unescape(data)
    data = re.sub(r'[ \t]+', ' ', data)
    data = re.sub(r'\n\s*\n+', '\n', data)
    return data.strip()

if __name__ == "__main__":
    # 澎湃首页提取链接
    data = fetch("https://www.thepaper.cn/")
    links = re.findall(r'href="(https?://www\.thepaper\.cn/newsDetail_forward_\d+)"[^>]*>(.*?)</a>', data, re.S)
    seen = set()
    print("########## 澎湃文章链接 ##########")
    for u, t in links:
        t = re.sub(r'<[^>]+>', '', t).strip()
        if u in seen or not t:
            continue
        seen.add(u)
        print(f"- {t[:60]} | {u}")
    print(f"total unique: {len(seen)}")

    # arXiv 镜像测试
    print("\n########## arXiv 镜像 ##########")
    for u in [
        "https://arxiv.org/list/cs.LG/recent",
        "http://arxiv.org/list/cs.LG/recent",
        "https://cn.arxiv.org/list/cs.LG/recent",
        "https://www.arxiv.org/list/cs.LG/recent",
        "https://arxiv.org/abs/2608.00001",
    ]:
        data = fetch(u)
        if data.startswith("ERR"):
            print(f"== {u}: {data}")
        else:
            txt = strip_html(data)
            print(f"== {u}: len={len(txt)}")
            print(txt[:400])
        time.sleep(0.8)
