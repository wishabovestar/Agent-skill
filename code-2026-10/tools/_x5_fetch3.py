# -*- coding: utf-8 -*-
"""补抓 3：Nature split attractor 正文 / Warp 博客文 / anthropic 案例页(jina 代理)"""
import ssl, sys, io, urllib.request
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=CTX))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
D = Path("D:/hermes/analysis/_x5")

def g(name, url, timeout=30, headers=None):
    h = {"User-Agent": UA, "Accept": "text/html,application/json,*/*", "Accept-Language": "en-US,en;q=0.9"}
    if headers: h.update(headers)
    try:
        with OPENER.open(urllib.request.Request(url, headers=h), timeout=timeout) as r:
            b = r.read()
        (D / name).write_bytes(b)
        print(f"OK   {name:34s} {r.status} {len(b):8d}")
        return b
    except Exception as e:
        print(f"FAIL {name:34s} {type(e).__name__} {str(e)[:70]}")

g("nat_split.html", "https://www.nature.com/articles/s41586-026-11144-9")
g("warp_post.html", "https://www.warp.dev/blog/self-improving-software-proactive-agents")
g("warp_jina.txt", "https://r.jina.ai/https://www.anthropic.com/customers/warp", timeout=45)
g("warp_jina2.txt", "https://r.jina.ai/https://www.anthropic.com/news/warp", timeout=45)
