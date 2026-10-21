# -*- coding: utf-8 -*-
import io, re, sys

PT = "D:/hermes/analysis/_pt/"
tag = sys.argv[1]
lines = io.open(PT + "x_%s.txt" % tag, encoding="utf-8", errors="replace").read().splitlines()
cand = []
for i, L in enumerate(lines):
    s = L.strip()
    if 0 < len(s) < 40 and re.match(r"(?i)^(\d+(\.\d+)*\.?\s*)?(results?|findings)\s*$", s):
        cand.append(i)
print("[%s] lines=%d results_headings=%s" % (tag, len(lines), cand))
if cand:
    st = cand[0]
    seg = [re.sub(r"\s+", " ", L).strip() for L in lines[st:st + 220]]
    withnum = [s for s in seg if len(s) > 60 and re.search(r"\d", s)]
    print("seg_lines=%d withnum=%d" % (len(seg), len(withnum)))
    for s in withnum[:22]:
        print(" - " + s[:300])
