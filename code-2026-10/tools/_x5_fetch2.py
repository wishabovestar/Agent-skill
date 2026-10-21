# -*- coding: utf-8 -*-
"""补抓：split attractor 元数据 / Warp 博客 / Nature 正文页"""
import ssl, sys, io, json, re, urllib.request, urllib.parse
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=CTX))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
D = Path("D:/hermes/analysis/_x5")

def g(name, url, timeout=25, headers=None):
    h = {"User-Agent": UA, "Accept": "application/json,text/html,*/*", "Accept-Language": "en-US,en;q=0.9"}
    if headers: h.update(headers)
    try:
        with OPENER.open(urllib.request.Request(url, headers=h), timeout=timeout) as r:
            b = r.read()
        (D / name).write_bytes(b)
        print(f"OK   {name:30s} {r.status} {len(b):8d}")
        return b
    except Exception as e:
        print(f"FAIL {name:30s} {type(e).__name__} {str(e)[:70]}")
        return None

# 1) Crossref 按标题精确查
q = urllib.parse.quote("A split attractor design for rapidly writing a navigational goal")
g("cr_split2.json", f"https://api.crossref.org/works?query.title={q}&rows=5&filter=from-pub-date:2026-01-01")
# 2) Nature 站内搜索
g("nat_search.html", "https://www.nature.com/search?q=%22split%20attractor%22&order=date_desc")
# 3) Nature 正文页（配体那篇）
g("nat_ligand.html", "https://www.nature.com/articles/s41586-026-11013-5")
# 4) Warp 博客多条候选
g("warp_w1.html", "https://www.anthropic.com/engineering/warp")
g("warp_w2.html", "https://warp.dev/blog")
g("hn_warp.json", "https://hn.algolia.com/api/v1/search?query=Warp%20self-improving%20agents&tags=story")
g("wb_warp.json", "http://archive.org/wayback/available?url=anthropic.com/customers/warp")
