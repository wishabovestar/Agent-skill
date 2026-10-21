# -*- coding: utf-8 -*-
"""arXiv 两篇 HTML → 结构化 digest（章节 / 表题 / 数字句）"""
import sys, io, re, html
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
D = Path("D:/hermes/analysis/_x5")

def clean(t):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"[ \t\r\f\v]+", " ", html.unescape(t).replace("\u00a0", " "))

def heads(raw):
    out, seen = [], set()
    for m in re.finditer(r"<(h[1-6])[^>]*>(.*?)</\1>", raw, re.S | re.I):
        s = re.sub(r"\s+", " ", clean(m.group(2))).strip()
        s = re.sub(r"^\d+(\.\d+)*\s*", "", s)
        if 3 < len(s) < 140 and s not in seen:
            seen.add(s); out.append(s)
    return out

def caps(raw):
    out = []
    for m in re.finditer(r'<(figcaption|table)[^>]*>(.*?)</(figcaption|table)>', raw, re.S | re.I):
        s = re.sub(r"\s+", " ", clean(m.group(2))).strip()
        if 20 < len(s) < 900:
            out.append(s)
    return out

def numsent(txt):
    out = []
    for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(])", txt):
        s = re.sub(r"\s+", " ", s).strip()
        if 35 < len(s) < 600 and re.search(r"\d", s) and re.search(r"[a-zA-Z]", s):
            out.append(s)
    return out

for src, dst in [("ax_2610.21601.html", "d_ax_opd.txt"), ("ax_2609.01836.html", "d_ax_eal.txt")]:
    raw = (D / src).read_text(encoding="utf-8", errors="ignore")
    txt = clean(raw)
    sn = numsent(txt)
    hs = heads(raw); cs = caps(raw)
    L = ["=== %s detag=%d ===" % (src, len(txt)), "", "--- HEADINGS ---"] + hs[:70]
    L += ["", "--- CAPTIONS/TABLES ---"] + [f"[{i}] {c}" for i, c in enumerate(cs, 1)][:25]
    L += ["", "--- NUMERIC SENTENCES (%d) ---" % len(sn)] + [f"{i}. {s}" for i, s in enumerate(sn, 1)]
    body = "\n".join(L)
    (D / dst).write_text(body, encoding="utf-8")
    print("%-14s %7d chars heads=%d caps=%d nums=%d" % (dst, len(body), len(hs), len(cs), len(sn)))
