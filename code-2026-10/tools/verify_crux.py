# -*- coding: utf-8 -*-
"""核对论文卡片里的每个数字是否真的出现在正文（逐字子串匹配）+ 负向对照。

规则：只承认 _crux.txt 里能 grep 到的数字；任何一条 FAIL 都必须从卡片里删掉或改口径。
"""
import io
import sys

SRC = r"D:/hermes/analysis/_crux.txt"
OUT = r"D:/hermes/analysis/_verify_crux.txt"

checks = [
    # (标签, 必须逐字出现的片段)
    ("86x 省算力", "86 times less compute"),
    ("6.4 GPU-hours", "6.4 GPU-hours"),
    ("主评估 25 crux/侧", "m = 25"),
    ("MM 重叠 13.4%", "13.4%"),
    ("MM 基线 39.2%", "39.2%"),
    ("MM SE 1.6", "1.6%"),
    ("gap 25.9", "25.9"),
    ("gap SE 1.2", "1.2 points"),
    ("p<1e-10", "10 − 10"),
    ("55 of 59", "55 of the 59 games"),
    ("single-rollout 18.8/25.1", "18.8% against 25.1%"),
    ("47 of 59", "47 of the 59 games"),
    ("6.4 points", "6.4 points"),
    ("26.8 a priori gap", "26.8"),
    ("coverage 28.6/37.8", "28.6% of the multiple-rollout cruxes against a baseline of 37.8%"),
    ("Metaculus 48.5/44.0", "48.5% against 44.0%"),
    ("Metaculus 39.9/70.9", "39.9%"),
    ("gap 31.0 ± 4.9", "31.0 ±"),
    ("p=1.2e-4", "1.2 × 10 − 4"),
    ("13 of 15", "13 of the 15 events"),
    ("contested 29 games", "29 contested games"),
    ("contested 16.0/40.5", "16.0%"),
    ("contested 26 below", "26 below their own baseline"),
    ("三档 25.9–36.1", "25.9 to 36.1"),
    ("specific gap 16.4 vs 24.7", "16.4 points"),
    ("fall 8.3 (5.1–11.5)", "5.1 to 11.5"),
    ("42 of 59", "42 of 59 games"),
    ("58 of 59", "58 of 59 games"),
    ("27 cells", "All 27 cells"),
    ("judgements 12,978", "12,978"),
    ("judgements 1,013,888", "1,013,888"),
    ("kappa MM 4.47", "4.47"),
    ("kappa MC 3.27", "3.27"),
    ("clusters 20.5", "20.5 clusters"),
    ("clusters 5.2", "5.2 per Metaculus event"),
    ("3.4 per rollout", "3.4 per rollout"),
    ("4 -> 28", "from 4 at two rollouts to 28 at nine"),
    ("36 pairs", "reaches 36"),
    ("5/9 -> 28% pairs 61% cruxes", "28% of the pairs yet 61%"),
    ("7 -> 83%", "seven give 83%"),
    ("751,515 pairs / 12 GPU-h", "751,515"),
    ("12 GPU-hours", "12 GPU-hours"),
    ("P=1,225", "1,225"),
    ("15 Metaculus events", "15 Metaculus events"),
    ("450 rollouts", "450 rollouts"),
    ("59 games", "59 of its games"),
    ("1,891 matchups", "1,891 possible matchups"),
    ("62 teams", "62 teams"),
    ("9 rollouts/game", "9 rollouts per game"),
    ("2,000 pairs judged", "2,000 March Madness crux pairs"),
    ("Qwen3-Reranker-8B", "Qwen3-Reranker-8B"),
    ("270 tokens", "270 tokens"),
    ("Metaculus 30 rollouts", "each of the 15 events received 30 rollouts"),
    ("live window", "2026-02-28 and 2026-03-18"),
]

# 负向对照：这些数字若"查到"说明匹配器太松（实际并不存在）
negatives = ["13.9%", "41.2%", "88 times less compute", "7.1 GPU-hours", "19.7%"]

txt = io.open(SRC, encoding="utf-8").read()
lines = []
ok = bad = 0
for label, frag in checks:
    hit = frag in txt
    ok += hit
    bad += (not hit)
    lines.append(f"{'PASS' if hit else 'FAIL'}  {label:<28} <<{frag}>>")

lines.append("")
lines.append("-- 负向对照（应全部 MISS）--")
for n in negatives:
    hit = n in txt
    lines.append(f"{'LEAK' if hit else 'MISS'}  {n}")

empty = sum(1 for _, f in checks if not f.strip())
summary = f"\n合计 PASS {ok} / FAIL {bad} / 空片段 {empty} / 条目 {len(checks)}"
io.open(OUT, "w", encoding="utf-8").write("\n".join(lines) + summary + "\n")
print(ok, bad, empty, len(checks))
sys.exit(1 if (bad or empty) else 0)
