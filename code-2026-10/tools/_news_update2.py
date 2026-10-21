# -*- coding: utf-8 -*-
"""新闻早报更新 v2 —— 可用源：新浪滚动 / IT之家 RSS / arXiv / WHO / HN + 广期所碳酸锂"""
import ssl, sys, io, json, re, time, urllib.request, urllib.parse
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=CTX))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

def fetch(url, timeout=25, referer=None, tries=2):
    for i in range(tries):
        try:
            h = {"User-Agent": UA, "Accept": "*/*"}
            if referer:
                h["Referer"] = referer
            with OPENER.open(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                print("  ERR", url[:55], type(e).__name__, str(e)[:60])
            time.sleep(2)
    return None

out = {"run_at": datetime.now().isoformat(timespec="seconds"), "sina": [], "ithome": [],
       "arxiv": [], "who": [], "hn": [], "price": None}

# 1) 新浪滚动（财经/国内综合）
raw = fetch("https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2515&k=&num=30&page=1")
if raw:
    d = json.loads(raw.decode("utf-8", "ignore"))
    for it in (d.get("result", {}).get("data") or []):
        t = (it.get("title") or "").strip()
        if t:
            out["sina"].append({"title": t, "url": it.get("url"), "time": it.get("ctime") or it.get("mtime"),
                                "intro": re.sub(r"\s+", " ", (it.get("intro") or ""))[:160]})
    print("sina", len(out["sina"]))

# 2) IT之家 RSS（科技）
raw = fetch("https://www.ithome.com/rss/")
if raw:
    try:
        root = ET.fromstring(raw)
        for it in root.iter("item"):
            t = (it.findtext("title") or "").strip()
            if t:
                out["ithome"].append({"title": t, "url": (it.findtext("link") or "").strip(),
                                      "pub": (it.findtext("pubDate") or "").strip(),
                                      "desc": re.sub(r"<[^>]+>", "", it.findtext("description") or "")[:200]})
        print("ithome", len(out["ithome"]))
    except Exception as e:
        print("ithome parse", e)

# 3) arXiv cs.AI 最新
raw = fetch("http://export.arxiv.org/rss/cs.AI")
if raw:
    try:
        root = ET.fromstring(raw)
        for it in list(root.iter("item"))[:20]:
            t = re.sub(r"\s+", " ", (it.findtext("title") or "")).strip()
            l = (it.findtext("link") or "").strip()
            if t:
                out["arxiv"].append({"title": t, "url": l, "date": (it.findtext("pubDate") or "").strip()})
        print("arxiv", len(out["arxiv"]))
    except Exception as e:
        print("arxiv parse", e)

# 4) WHO DON（疫情）
raw = fetch("https://www.who.int/api/news/diseaseoutbreaknews")
if raw:
    try:
        d = json.loads(raw.decode("utf-8", "ignore"))
        vals = d.get("value") or d if isinstance(d, list) else d.get("value", [])
        for it in (vals or [])[:12]:
            out["who"].append({"title": (it.get("Title") or it.get("title") or "").strip(),
                               "date": (it.get("PublicationDateAndTime") or it.get("date") or "")[:10],
                               "url": it.get("UrlName") or it.get("url")})
        print("who", len(out["who"]))
    except Exception as e:
        print("who parse", e)

# 5) HN 首页
raw = fetch("https://hn.algolia.com/api/v1/search?tags=front_page")
if raw:
    try:
        d = json.loads(raw.decode("utf-8", "ignore"))
        for it in (d.get("hits") or [])[:15]:
            if it.get("title"):
                out["hn"].append({"title": it["title"], "points": it.get("points"),
                                  "url": it.get("url") or f"https://news.ycombinator.com/item?id={it.get('objectID')}"})
        print("hn", len(out["hn"]))
    except Exception as e:
        print("hn parse", e)

# 6) 广期所碳酸锂主连（新浪行情）
raw = fetch("https://hq.sinajs.cn/list=nf_LC0", referer="https://finance.sina.com.cn")
if raw:
    txt = raw.decode("gbk", "ignore")
    out["price"] = {"raw": txt.strip()[:600]}
    print("price", txt.strip()[:150])

stamp = datetime.now().strftime("%Y%m%d_%H%M")
p = Path(f"D:/hermes/analysis/_news_update2_{stamp}.json")
p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("SAVED", p.name, "sina", len(out["sina"]), "ith", len(out["ithome"]), "ax", len(out["arxiv"]),
      "who", len(out["who"]), "hn", len(out["hn"]), "price", bool(out["price"]))
