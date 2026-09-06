# -*- coding: utf-8 -*-
"""批量提取 arXiv abs 页摘要"""
import re, html, glob

for f in sorted(glob.glob(r"D:\hermes\hermes-data\profiles\qqbot3\cache\kv_2609*.html")):
    raw = open(f, encoding="utf-8", errors="ignore").read()
    aid = re.search(r"arxiv.org/abs/(\d+\.\d+)", raw) or re.search(r"citation_arxiv_id\" content=\"(\d+\.\d+)", raw)
    t = re.search(r'<h1 class="title[^"]*">(.*?)</h1>', raw, re.S)
    m = re.search(r'name="citation_abstract" content="(.*?)"', raw) or re.search(r'<blockquote class="abstract[^"]*">(.*?)</blockquote>', raw, re.S)
    print("=" * 58)
    print("ID:", aid.group(1) if aid else f)
    if t:
        print("标题:", html.unescape(re.sub(r"<[^>]+>", "", t.group(1))).strip()[:120])
    if m:
        ab = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
        print("摘要:", re.sub(r"\s+", " ", ab)[:950])
    print()
