# -*- coding: utf-8 -*-
"""解析 Crossref / arXiv 元数据 → 可读摘要"""
import sys, io, json, re
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
D = Path("D:/hermes/analysis/_x5")
L = []

def cr(name, label):
    p = D / name
    if not p.exists():
        L.append(f"## {label}: MISSING"); return
    d = json.loads(p.read_text(encoding="utf-8"))["message"]
    L.append(f"## {label}")
    L.append("TITLE: " + " | ".join(d.get("title") or []))
    L.append("DOI: " + (d.get("DOI") or ""))
    L.append("JOURNAL: " + str((d.get("container-title") or [""])[0]) + " vol=" + str(d.get("volume")) +
             " page=" + str(d.get("page")) + " article=" + str(d.get("article-number")))
    for k in ("published-print", "published-online", "created"):
        if d.get(k, {}).get("date-parts"):
            L.append(f"{k}: {d[k]['date-parts'][0]}")
    L.append("TYPE: " + str(d.get("type")))
    au = d.get("author") or []
    L.append("AUTHORS: " + "; ".join(f"{a.get('given','')} {a.get('family','')}".strip() for a in au[:12]) +
             (f"  (共{len(au)}人)" if len(au) > 12 else ""))
    ab = re.sub(r"<[^>]+>", " ", d.get("abstract") or "")
    L.append("ABSTRACT_LEN: %d" % len(ab))
    L.append("ABSTRACT: " + re.sub(r"\s+", " ", ab)[:2000])
    L.append("")

cr("cr_ligand.json", "Nature DOI 10.1038/s41586-026-11013-5")
cr("cr_split.json", "Crossref search: split attractor")

x = (D / "ax_ids.xml").read_text(encoding="utf-8")
L.append("## arXiv API")
for m in re.finditer(r"<entry>(.*?)</entry>", x, re.S):
    e = m.group(1)
    g = lambda t: (re.search(rf"<{t}[^>]*>(.*?)</{t}>", e, re.S) or [None, ""])[1]
    L.append("ID: " + re.sub(r"\s+", " ", g("id")))
    L.append("TITLE: " + re.sub(r"\s+", " ", g("title")).strip())
    L.append("PUB: " + g("published").strip() + "  UPD: " + g("updated").strip())
    L.append("AUTH: " + "; ".join(re.findall(r"<name>(.*?)</name>", e)[:10]))
    L.append("COMMENT: " + re.sub(r"\s+", " ", g("arxiv:comment")).strip())
    L.append("PRIMARY: " + g("arxiv:primary_category"))
    L.append("ABS: " + re.sub(r"\s+", " ", g("summary")).strip()[:1400])
    L.append("")
out = "\n".join(L)
Path("D:/hermes/analysis/_x5_meta.txt").write_text(out, encoding="utf-8")
print("WROTE", len(out), "chars", len(L), "lines")
