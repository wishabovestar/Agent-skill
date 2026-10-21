# -*- coding: utf-8 -*-
import io, re, sys
PT = "D:/hermes/analysis/_pt/"
tag = sys.argv[1]
txt = io.open(PT + "x_%s.txt" % tag, encoding="utf-8", errors="replace").read()
txt = txt[: int(len(txt) * 0.66)]
flat = re.sub(r"\s+", " ", txt)
sents = re.split(r"(?<=[.!?])\s+", flat)
pat = re.compile(r"(p\s*[=<>]\s*0?\.\d+|η2|ηp|β\s*=|r\s*=\s*[-−]?0?\.\d+|OR\s*=|Cohen|d\s*=\s*0?\.\d+)", re.I)
sel = [s.strip() for s in sents if re.search(r"\d", s) and pat.search(s) and 50 < len(s) < 330]
seen, out = set(), []
for s in sel:
    k = s[:45]
    if k not in seen:
        seen.add(k); out.append(s)
print("[%s] n_pat=%d" % (tag, len(out)))
for s in out[:20]:
    print(" - " + s)
