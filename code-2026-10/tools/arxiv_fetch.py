#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第八轮：arXiv 最新论文抓取解析"""
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

def parse_arxiv_list(data, max_items=40):
    """解析 arxiv list 页面"""
    # 每条: <dt>...<a href="/abs/XXXX.XXXXX" ...>arXiv:XXXX</a> ... </dt> <dd>... Title: ...
    items = []
    # 分割 dt/dd 对
    blocks = re.findall(r'<dt>(.*?)</dt>\s*<dd>(.*?)</dd>', data, re.S)
    for dt, dd in blocks[:max_items]:
        m = re.search(r'href="(/abs/[\d.]+)"[^>]*>([^<]+)</a>', dt)
        if not m:
            continue
        pid = m.group(2).strip().replace('arXiv:', '')
        # title
        tm = re.search(r'<div class="list-title[^"]*">(.*?)</div>', dd, re.S)
        title = ''
        if tm:
            title = re.sub(r'<[^>]+>', '', tm.group(1))
            title = re.sub(r'^\s*Title:\s*', '', title).strip()
        # authors (简化)
        am = re.search(r'<div class="list-authors[^"]*">(.*?)</div>', dd, re.S)
        authors = ''
        if am:
            authors = re.sub(r'<[^>]+>', '', am.group(1))
            authors = re.sub(r'^\s*Authors:\s*', '', authors).strip()[:80]
        items.append({"id": pid, "title": title, "authors": authors})
    return items

if __name__ == "__main__":
    print("########## arXiv cs.LG recent (前40) ##########")
    data = fetch("https://arxiv.org/list/cs.LG/recent")
    if data.startswith("ERR"):
        print(data)
    else:
        items = parse_arxiv_list(data, 40)
        for i, it in enumerate(items, 1):
            print(f"{i}. [{it['id']}] {it['title']} | {it['authors'][:60]}")
        print(f"\nTOTAL PARSED: {len(items)}")

    time.sleep(1.0)
    print("\n\n########## arXiv 锂电搜索 ##########")
    # 用 arxiv 搜索页面
    data2 = fetch("https://arxiv.org/search/?searchtype=all&query=lithium+battery+solid+state&start=0")
    if data2.startswith("ERR"):
        print(data2)
    else:
        # 搜索页解析
        results = re.findall(r'<li class="arxiv-result">(.*?)</li>', data2, re.S)
        print(f"results found: {len(results)}")
        for r in results[:12]:
            tm = re.search(r'<p class="title[^"]*">(.*?)</p>', r, re.S)
            title = re.sub(r'<[^>]+>', '', tm.group(1)).strip() if tm else '?'
            pm = re.search(r'href="(https?://arxiv\.org/abs/[\d.]+)"', r)
            pid = pm.group(1).split('/abs/')[-1] if pm else '?'
            dm = re.search(r'<p class="abstract[^"]*">(.*?)</p>', r, re.S)
            abstract = re.sub(r'<[^>]+>', '', dm.group(1)).strip()[:180] if dm else ''
            print(f"- [{pid}] {title}\n    {abstract}")
