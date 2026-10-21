# -*- coding: utf-8 -*-
import io, os, re, sys

PT = "D:/hermes/analysis/_pt/"
tag = sys.argv[1]
txt = io.open(PT + "x_%s.txt" % tag, encoding="utf-8", errors="replace").read()
flat = re.sub(r"\s+", " ", txt)
m = re.search(r"(?i)\b(results?)\b\s*[:.]?\s", flat)
start = m.start() if m else 0
m2 = re.search(r"(?i)\b(discussion|limitations?)\b", flat[start + 10:])
end = start + 10 + m2.start() if m2 else len(flat)
seg = flat[start:end]
print("[%s] results_seg_chars=%d pos=%d" % (tag, len(seg), start))
sents = re.split(r"(?<=[.!?])\s+", seg)
sel = [s.strip() for s in sents if re.search(r"\d", s) and 40 < len(s) < 320]
print("n=%d" % len(sel))
for s in sel[:20]:
    print(" - " + s)
