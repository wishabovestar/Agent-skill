# -*- coding: utf-8 -*-
"""从 4 份 HTML 抽取：标题层级 / 图注 / 含数字句 → 各一份 digest"""
import sys, io, re, html
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
D = Path("D:/hermes/analysis/_x5")

def clean(t):
    t = re.sub(r"<script.*?</script>|<style.*?</style>|<nav.*?</nav>|<footer.*?</footer>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = t.replace("\u00a0", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", t)

def heads(raw):
    hs = []
    for m in re.finditer(r"<(h[1-3])[^>]*>(.*?)</\1>", raw, re.S | re.I):
        s = re.sub(r"\s+", " ", clean(m.group(2))).strip()
        if 3 < len(s) < 130:
            hs.append(f"{m.group(1).lower()}: {s}")
    seen, out = set(), []
    for h in hs:
        if h not in seen:
            seen.add(h); out.append(h)
    return out

def caps(raw):
    out = []
    for m in re.finditer(r'<(figcaption|div class="[^"]*c-article-section__figure-description[^"]*")[^>]*>(.*?)</(figcaption|div)>', raw, re.S | re.I):
        s = re.sub(r"\s+", " ", clean(m.group(2))).strip()
        if len(s) > 30:
            out.append(s[:600])
    return out

def numsent(txt):
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", txt)
    out = []
    for s in sents:
        s = re.sub(r"\s+", " ", s).strip()
        if 30 < len(s) < 600 and re.search(r"\d", s) and re.search(r"[a-zA-Z]", s):
            out.append(s)
    return out

JOBS = [("nat_ligand.html", "d_ligand.txt"), ("nat_split.html", "d_split.txt"),
        ("warp_post.html", "d_warp.txt")]
for src, dst in JOBS:
    raw = (D / src).read_text(encoding="utf-8", errors="ignore")
    txt = clean(raw)
    L = ["=== SOURCE %s raw=%d detag=%d ===" % (src, len(raw), len(txt)), "", "--- HEADINGS ---"]
    L += heads(raw)[:60]
    L += ["", "--- FIGCAPS ---"]
    L += [f"[{i}] {c}" for i, c in enumerate(caps(raw), 1)][:30]
    L += ["", "--- NUMERIC SENTENCES (%d) ---" % len(numsent(txt))]
    sn = numsent(txt)
    L += [f"{i}. {s}" for i, s in enumerate(sn, 1)]
    out = "\n".join(L)
    (D / dst).write_text(out, encoding="utf-8")
    print(f"{dst:14s} {len(out):8d} chars  heads={len(heads(raw))} caps={len(caps(raw))} nums={len(sn)}")
