#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第九轮：arXiv cs.LG recent 修正解析 + AI 主题搜索 + GitHub trending 尝试"""
import subprocess, re, html, time, json

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
    s = re.sub(r'<[^>]+>', ' ', s)
    s = html.unescape(s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

def parse_arxiv_search(data, n=15):
    results = re.findall(r'<li class="arxiv-result">(.*?)</li>', data, re.S)
    out = []
    for r in results[:n]:
        tm = re.search(r'<p class="title[^"]*">(.*?)</p>', r, re.S)
        title = strip_tags(tm.group(1)) if tm else '?'
        pm = re.search(r'href="(https?://arxiv\.org/abs/[\d.]+)"', r)
        pid = pm.group(1).split('/abs/')[-1] if pm else '?'
        dm = re.search(r'<p class="abstract[^"]*">(.*?)</p>', r, re.S)
        abstract = strip_tags(dm.group(1))[:200] if dm else ''
        jm = re.search(r'<span class="tag is-small">([^<]+)</span>', r)
        journal = jm.group(1).strip() if jm else ''
        out.append({"id": pid, "title": title, "abstract": abstract, "journal": journal})
    return out

if __name__ == "__main__":
    queries = [
        ("transformer LLM", "transformer language model"),
        ("diffusion", "diffusion model"),
        ("graph neural network", "graph neural network"),
        ("reinforcement learning", "reinforcement learning agent"),
        ("multimodal", "multimodal vision language"),
    ]
    for label, q in queries:
        qq = q.replace(' ', '+')
        data = fetch(f"https://arxiv.org/search/?searchtype=all&query={qq}&start=0")
        print(f"\n########## arXiv: {label} ##########")
        if data.startswith("ERR"):
            print(data)
            continue
        items = parse_arxiv_search(data, 8)
        for it in items:
            print(f"- [{it['id']}] {it['title']} | {it['journal']}")
            if it['abstract']:
                print(f"    {it['abstract'][:150]}")
        time.sleep(1.0)

    print("\n\n########## GitHub trending 尝试 ##########")
    # 尝试 raw 风格 + 其他镜像
    for u in [
        "https://raw.githubusercontent.com/trending",
        "https://github.com/trending?since=daily",
        "https://hub.fastgit.org/trending",
        "https://github.moeyy.xyz/https://github.com/trending",
    ]:
        data = fetch(u)
        if data.startswith("ERR") or not data.strip():
            print(f"== {u}: EMPTY/ERR")
            continue
        txt = strip_tags(data)
        print(f"== {u}: len={len(txt)}")
        print(txt[:600])
        time.sleep(0.8)
