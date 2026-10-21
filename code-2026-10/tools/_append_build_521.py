# -*- coding: utf-8 -*-
"""Compose _append_511_521.md from the two card files. Prints verifiable counts."""
import io, os, re

A = r"D:/hermes/analysis/_cards/cards_511_515.md"
B = r"D:/hermes/analysis/_cards/cards_516_521.md"
OUT = r"D:/hermes/analysis/_append_511_521.md"

def rd(p):
    with io.open(p, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

a = rd(A)
a = a.replace("# 卡片 511–515 · Harness2 五篇全选（2026-10-20）",
              "## Harness2 五篇（511–515）· 2026-10-20", 1)
b = rd(B)
body = a.rstrip() + "\n\n---\n\n" + b.rstrip() + "\n"
with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(body)

n = body.count("\n") + 1
ents = re.findall(r"(?m)^### (\d{3})\.", body)
print("OUT bytes=%d lines=%d entries=%d" % (len(body.encode("utf-8")), n, len(ents)))
print("entry_ids=%s" % ",".join(ents))
missing = [i for i in range(511, 522) if str(i) not in ents]
print("missing=%s" % (missing if missing else "NONE"))
