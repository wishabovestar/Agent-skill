# -*- coding: utf-8 -*-
"""批量抓取：Warp博客 / Nature x2 / arXiv x2 / GitHub eal-bench"""
import ssl, sys, io, json, re, base64, urllib.request, urllib.parse
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=CTX))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
OUT = Path("D:/hermes/analysis/_x5")
OUT.mkdir(exist_ok=True)

def fetch(name, url, timeout=30, headers=None, tries=2):
    h = {"User-Agent": UA, "Accept": "application/json,text/html,application/xml,*/*"}
    if headers: h.update(headers)
    for i in range(tries):
        try:
            with OPENER.open(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                b = r.read()
            (OUT / name).write_bytes(b)
            print(f"OK   {name:34s} {r.status} {len(b):8d} {r.headers.get('Content-Type','?')[:40]}")
            return b
        except Exception as e:
            if i == tries - 1:
                print(f"FAIL {name:34s} {type(e).__name__} {str(e)[:90]}")

# 1 Warp 博客（Anthropic customer story）
fetch("warp_anthropic.html", "https://www.anthropic.com/customers/warp")
fetch("warp_news.html", "https://www.anthropic.com/news/warp")
# 2 Nature DOI（配体优化 / random background）
fetch("cr_ligand.json", "https://api.crossref.org/works/10.1038/s41586-026-11013-5")
# 3 Nature split attractor 检索
q = urllib.parse.quote("A split attractor design for rapidly writing a navigational goal")
fetch("cr_split.json", f"https://api.crossref.org/works?query.bibliographic={q}&rows=5")
# 4 arXiv 两条
fetch("ax_ids.xml", "http://export.arxiv.org/api/query?id_list=2610.21601,2609.01836&max_results=5")
# 5 arXiv HTML 全文
fetch("ax_2610.21601.html", "https://arxiv.org/html/2610.21601v1")
fetch("ax_2609.01836.html", "https://arxiv.org/html/2609.01836v1")
# 6 GitHub 仓库 + README
fetch("gh_repo.json", "https://api.github.com/repos/tommasocerruti/eal-bench")
rd = fetch("gh_readme.json", "https://api.github.com/repos/tommasocerruti/eal-bench/readme")
if rd:
    try:
        d = json.loads(rd.decode("utf-8", "ignore"))
        txt = base64.b64decode(d.get("content", "")).decode("utf-8", "ignore")
        (OUT / "gh_readme.md").write_text(txt, encoding="utf-8")
        print("README_BYTES", len(txt.encode("utf-8")))
    except Exception as e:
        print("readme decode err", e)
print("DONE")
