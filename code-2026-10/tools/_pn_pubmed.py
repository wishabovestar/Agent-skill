# -*- coding: utf-8 -*-
import glob, io, json, re

def txt(x):
    x = re.sub(r"<[^>]+>", " ", x)
    return re.sub(r"\s+", " ", x).strip()

out = {}
for fp in sorted(glob.glob("D:/hermes/analysis/_pn/pm_*.xml")):
    x = io.open(fp, encoding="utf-8", errors="replace").read()
    pmid = fp.split("pm_")[-1].replace(".xml", "")
    doi = (re.search(r"<ArticleId IdType=\"doi\">(.*?)</ArticleId>", x) or [None, ""])[1]
    ab = " | ".join(txt(m) for m in re.findall(r"<Abstract>(.*?)</Abstract>", x, re.S))
    ab = txt(ab)
    ti = txt((re.search(r"<ArticleTitle>(.*?)</ArticleTitle>", x, re.S) or [None, ""])[1])
    jr = txt((re.search(r"<Title>(.*?)</Title>", x, re.S) or [None, ""])[1])
    out[doi] = ab
    print("PMID=%s DOI=%s jr=%s" % (pmid, doi, jr[:40]))
    print("  TITLE %s" % ti[:110])
    print("  ABS len=%d" % len(ab))

old = json.load(io.open("D:/hermes/analysis/_pn/abstracts.json", encoding="utf-8"))
for k, v in out.items():
    if v and (not old.get(k) or len(v) > len(old.get(k, ""))):
        old[k] = v
json.dump(old, io.open("D:/hermes/analysis/_pn/abstracts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("MERGED n=%d total_chars=%d" % (len(old), sum(len(v) for v in old.values())))

n = io.open("D:/hermes/analysis/_pn/t_nature.html", encoding="utf-8", errors="replace").read()
for k in ["Methods", "Results", "Discussion", "Access through", "subscription", "This is a preview"]:
    print("NATURE %s = %d" % (k, n.count(k)))
