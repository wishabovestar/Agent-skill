# -*- coding: utf-8 -*-
"""P0 卡片数字核验：卡片里出现的每个数字型 token，是否逐字出现在对应原文 txt 里。
不是「每个数字都必须出现」（换算/推导数字不出现很正常），而是看缺失率与缺失 Top，
缺失率高或关键指标缺失即为红旗。"""
import io
import os
import re

D = r"D:/hermes/analysis"
IDS = ["2610.21165", "2610.21170", "2610.22209", "2610.17611", "2610.23371"]
TOK = re.compile(r"\d+(?:\.\d+)?")

for pid in IDS:
    card_p = os.path.join(D, "_cards", pid + ".md")
    src_p = os.path.join(D, "_p0_" + pid + ".txt")
    card = io.open(card_p, encoding="utf-8", errors="replace").read()
    src = io.open(src_p, encoding="utf-8", errors="replace").read()
    src_flat = re.sub(r"\s+", "", src)

    toks = {}
    for m in TOK.finditer(card):
        t = m.group(0)
        if len(t.replace(".", "")) < 2:
            continue
        toks[t] = toks.get(t, 0) + 1

    miss = []
    for t, c in toks.items():
        if t not in src and re.sub(r"\s+", "", t) not in src_flat:
            miss.append((c, t))
    miss.sort(reverse=True)
    hit = len(toks) - len(miss)
    cov = 100.0 * hit / max(1, len(toks))
    print("%s  tokens=%d hit=%d miss=%d cov=%.1f%%" % (pid, len(toks), hit, len(miss), cov))
    if miss:
        print("   miss_top: " + ", ".join("%s(x%d)" % (t, c) for c, t in miss[:12]))
    else:
        print("   miss_top: -")
