# -*- coding: utf-8 -*-
"""巡天 算法/数学/计算机原理/DL 知识采集 - 采集器"""
import ssl, urllib.request, urllib.parse, json, os, time, re, sys, datetime

BASE = r"D:/hermes/data/agent_knowledge"
OUT = os.path.join(BASE, "algorithm")
RAW = os.path.join(OUT, "tmp")
os.makedirs(RAW, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

def fetch(url, timeout=30, accept="application/json"):
    ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    req = urllib.request.Request(url, headers={
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept":accept})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", errors="ignore")

# ---------- arXiv ----------
ARXIV_CATS = {
    "algorithm": ["cs.DS"],
    "math":      ["math.NA", "math.OC", "math.ST"],
    "system":    ["cs.AR", "cs.PL", "cs.DC"],
    "dl":        ["cs.LG"],
    "ml":        ["stat.ML"],
    "neural":    ["cs.CL", "cs.CV", "cs.NE"],
}
arxiv_out = {}
for direction, cats in ARXIV_CATS.items():
    arxiv_out[direction] = []
    for cat in cats:
        url = ("http://export.arxiv.org/api/query?search_query=cat:%s"
               "&sortBy=submittedDate&sortOrder=descending&max_results=8" % cat)
        try:
            xml = fetch(url, timeout=35, accept="application/atom+xml")
        except Exception as e:
            print("ARXIV_ERR", cat, type(e).__name__, str(e)[:60]); continue
        entries = re.findall(r"<entry>(.*?)</entry>", xml, re.S)
        for e in entries:
            t = re.search(r"<title>(.*?)</title>", e, re.S)
            i = re.search(r"<id>(.*?)</id>", e, re.S)
            p = re.search(r"<published>(.*?)</published>", e, re.S)
            s = re.search(r"<summary>(.*?)</summary>", e, re.S)
            au = re.findall(r"<name>(.*?)</name>", e, re.S)
            if not (t and i): continue
            arxiv_out[direction].append({
                "cat": cat,
                "title": re.sub(r"\s+", " ", t.group(1)).strip(),
                "id": i.group(1).strip(),
                "published": (p.group(1).strip() if p else ""),
                "authors": au[:4],
                "summary": re.sub(r"\s+", " ", s.group(1)).strip()[:400] if s else "",
            })
        time.sleep(3)
json.dump(arxiv_out, open(os.path.join(RAW, "arxiv_raw.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
tot = sum(len(v) for v in arxiv_out.values())
print("ARXIV_DONE total=%d" % tot, {k: len(v) for k, v in arxiv_out.items()})
