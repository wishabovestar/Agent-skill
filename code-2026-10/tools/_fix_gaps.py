# -*- coding: utf-8 -*-
import io, re, os

# ---------- A) 522 题名/作者：从 arXiv abs 页取 ----------
p = "D:/hermes/analysis/_rd/abs_2607.11521.html"
print("[A] exists=%s size=%d" % (os.path.exists(p), os.path.getsize(p) if os.path.exists(p) else -1))
if os.path.exists(p):
    h = io.open(p, encoding="utf-8", errors="replace").read()
    m = re.search(r'<h1 class="title[^"]*">(.*?)</h1>', h, re.S)
    t = re.sub(r"<[^>]+>", "", m.group(1)) if m else "TITLE_MISS"
    t = re.sub(r"\s+", " ", t).strip()
    a = re.search(r'<div class="authors">(.*?)</div>', h, re.S)
    au = re.sub(r"<[^>]+>", "", a.group(1)) if a else "AUTH_MISS"
    au = re.sub(r"\s+", " ", au).strip()
    d = re.search(r'<div class="dateline">(.*?)</div>', h, re.S)
    dl = re.sub(r"<[^>]+>", "", d.group(1)) if d else "DL_MISS"
    dl = re.sub(r"\s+", " ", dl).strip()
    print("[A] TITLE=%s" % t)
    print("[A] AUTHORS=%s" % au)
    print("[A] DATELINE=%s" % dl)

# ---------- B) 525 SWE-bench Verified 主表：从 PDF 文本抓 ----------
q = "D:/hermes/analysis/_rd/pdf_2610.24453.txt"
lines = io.open(q, encoding="utf-8", errors="replace").read().splitlines()
print("[B] pdf_lines=%d" % len(lines))
hits = [i for i, L in enumerate(lines) if "SWE" in L or "Resolution" in L or "Resolved" in L]
print("[B] swe_hits=%d first10=%s" % (len(hits), hits[:10]))
for i in hits[:10]:
    print("[B] %d | %s" % (i, lines[i].strip()[:160]))
