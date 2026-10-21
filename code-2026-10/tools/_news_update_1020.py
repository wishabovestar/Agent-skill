# -*- coding: utf-8 -*-
"""新闻早报更新 2026-10-20 —— Bing News RSS + arXiv 最新 + 关键词"""
import ssl, sys, io, json, re, time, urllib.request, urllib.parse
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                     urllib.request.HTTPSHandler(context=CTX))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

def get(url, timeout=25, tries=2):
    for i in range(tries):
        try:
            with OPENER.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                print("  ERR", url[:60], type(e).__name__, str(e)[:70])
            time.sleep(2)
    return None

TOPICS = [
    ("AI模型/厂商", "%E4%BA%BA%E5%B7%A5%E6%99%BA%E8%83%BD%20%E5%A4%A7%E6%A8%A1%E5%9E%8B"),
    ("锂电/储能", "%E9%94%82%E7%94%B5%20%E5%82%A8%E8%83%BD"),
    ("病毒/流感", "%E6%B5%81%E6%84%9F%20%E7%97%85%E6%AF%92%E5%8F%98%E5%BC%82%E6%A0%AA"),
    ("半导体/算力", "%E5%8D%8A%E5%AF%BC%E4%BD%93%20%E7%AE%97%E5%8A%9B"),
    ("固态电池", "%E5%9B%BA%E6%80%81%E7%94%B5%E6%B1%A0"),
]
items = []
for tag, q in TOPICS:
    url = f"https://cn.bing.com/news/search?q={q}&format=rss"
    raw = get(url)
    if not raw:
        print(f"[{tag}] FAIL"); continue
    try:
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"[{tag}] XML_ERR {e}"); continue
    n = 0
    for it in root.iter("item"):
        t = (it.findtext("title") or "").strip()
        l = (it.findtext("link") or "").strip()
        d = (it.findtext("pubDate") or "").strip()
        desc = re.sub(r"<[^>]+>", "", it.findtext("description") or "").strip()
        if t:
            items.append({"topic": tag, "title": re.sub(r"\s+", " ", t), "link": l,
                          "pub": d, "desc": re.sub(r"\s+", " ", desc)[:300]})
            n += 1
    print(f"[{tag}] items={n}")
    time.sleep(2)

# arXiv 最新 AI 论文
papers = []
for cat in ["cs.AI", "cs.LG", "cs.SE"]:
    url = ("http://export.arxiv.org/api/query?search_query=cat:" + cat +
           "&max_results=6&sortBy=submittedDate&sortOrder=descending")
    raw = get(url)
    if not raw: 
        print(f"[ax:{cat}] FAIL"); continue
    txt = raw.decode("utf-8", "ignore")
    for e in re.findall(r"<entry>(.*?)</entry>", txt, re.S):
        m = re.search(r"<id>(.*?)</id>", e); t = re.search(r"<title>(.*?)</title>", e, re.S)
        p = re.search(r"<published>(.*?)</published>", e)
        if m and t:
            papers.append({"cat": cat, "id": m.group(1).replace("http://arxiv.org/abs/", ""),
                           "title": re.sub(r"\s+", " ", t.group(1)).strip(),
                           "date": p.group(1)[:10] if p else ""})
    print(f"[ax:{cat}] got")
    time.sleep(2)

stamp = datetime.now().strftime("%Y%m%d_%H%M")
p = Path(f"D:/hermes/analysis/_news_update_{stamp}.json")
p.write_text(json.dumps({"run_at": datetime.now().isoformat(timespec="seconds"),
                         "news": items, "papers": papers}, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"SAVED {p.name} news={len(items)} papers={len(papers)}")
