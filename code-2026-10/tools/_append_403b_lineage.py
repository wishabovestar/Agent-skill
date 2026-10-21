#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「版块 3 谱系追查」指针插入主归档的 #403 块（块尾 = 下一个 '## 本区统计' 之前）。先备份。"""
import shutil
from pathlib import Path

P = Path("D:/hermes/analysis/PAPER_ARCHIVE_agent_memory_swarm_2026-10.md")
BAK = P.with_suffix(".md.bak_20261016_lineage")
shutil.copy2(P, BAK)
print("备份 →", BAK, BAK.stat().st_size, "B")

with open(P, encoding="utf-8", newline="") as f:
    raw = f.read()
lines = raw.splitlines(keepends=True)
print("总行数:", len(lines))

# 找 #403 的起点行
i403 = next(i for i, l in enumerate(lines) if l.startswith("### 403."))
# 找它之后最近的 '## 本区统计' 作为块尾
j = next(i for i in range(i403 + 1, len(lines)) if lines[i].startswith("## 本区统计"))
print(f"#403 块 = 行 {i403+1} .. {j}（块尾 = 行 j+1='{lines[j].strip()[:30]}'）")

if "版块 3" in raw:
    print("已含指针，跳过"); raise SystemExit(0)

POINT = [
    "\n",
    "- **附（版块 3 · 2026-10-16）谱系追查**（子代理初查 + **本人 arXiv API 一手复核**）：\n",
    "  **最直接前作** = Pan et al. 2026 `arXiv:2606.05922`《Evolving Agents in the Dark: Retrospective Harness Optimization》（n=8，末位 X. Jia 与本文 References 逐字吻合）；"
    "次为 Karten et al. 2026 `2605.09998`（Continual Harness）。\n",
    "  **三基准全部第三方既有**（非自建）：CL-Bench = Asawa et al. `2606.05661`（全名 *Continual Learning Bench*）｜MemoryBench = Ai et al. `2510.17281`（清华 IR 组）｜MemoryArena = He et al. `2602.16313`；作者集与本文 7 人**无交集**。\n",
    "  **novelty** = 组合式微创新：8 组机制检索全 0 命中、无更早完全同机制，但近邻已被 2026-06～09 的 5 篇（`2609.35738`/`2609.32805`/`2608.21867`/`2609.39143`/`2606.05922`）分别占据侧面。\n",
    "  **引用数 = 0**（OpenAlex `W7221536561` 独立复现；`all:\"recurrent harness\"` totalResults=1 ⇒ 术语独占）。\n",
    "  **核验纪律**：15/15 候选 ID 由本人 arXiv API 逐个反查命中，含 3 个真实经典（Reflexion `2303.11366`/MemGPT `2310.08560`/Generative Agents `2304.03442`）作 **sanity 锚**。"
    "**未核实**：DoT（Lingam 2025）与 *Textual SGD*（Li & Huang 2026，totalResults=0）均未检到 ID，未凭记忆补。\n",
    "  报告 → `paper_deepread/reharness/lineage_20261016.md`（6,646 B）；卡内附节 → `paper_deepread/reharness/card.md`\n",
]

out = lines[:j] + POINT + lines[j:]
with open(P, "w", encoding="utf-8", newline="") as f:
    f.write("".join(out))
print("插入完成。新行数:", len(out), "| 新大小:", P.stat().st_size, "B")
