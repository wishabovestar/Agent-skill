# -*- coding: utf-8 -*-
import glob, io, os, re, shutil, time

ARC = sorted([p for p in glob.glob("D:/hermes/analysis/PAPER_ARCHIVE_agent_memory_swarm_2026-10*.md")
              if ".bak" not in os.path.basename(p)])[-1]
ENT = u"""
### 528. 勘误回填：522 题名/作者 · 525 SWE-bench Verified 主表（2026-10-20）

> 回填来源：`_rd/abs_2607.11521.html`、`_rd/pdf_2610.24453.txt`（pdf_lines=1838），逐字子串核验 n 命中。

**522（arXiv:2607.11521）补齐**
- 题名（abs 页 `<h1 class="title">` 逐字）：**Capturing the calendering U-shape in lithium-ion electrode thermal conductivity**
- 作者：**Julius Störk（1 人，单作者）**；Dateline：[Submitted on 13 Jul 2026]
- 类别：cond-mat.mtrl-sci / physics.chem-ph

**525（arXiv:2610.24453, Hippo）SWE-bench Verified 主表（Table 2，全 500 题，resolution rate）**
| backbone | No Memory | Hippo |
|---|---|---|
| GPT-5.6 Sol | 81.5±0.4 | 88.5±1.2 |
| Claude Haiku 4.5 | 62.6±0.2 | 70.7±1.4 |
| Gemini 3 Flash Preview | 74.2±0.4 | 81.6±1.4 |
| Qwen3.5-27B | 68.8±0.6 | 76.5±1.8 |

- WebArena（Table 1，列 Shopping 187 / Admin 182 / GitLab 180 / Reddit 106 / Map 109 / Overall 764）overall：64.2±1.2 → 72.9±1.0（+8.7）；33.8→42.5；39.0→46.4；35.8→43.6。
- 成本（WebArena / GPT-5.6 Sol）：actor 平均调用 69.27 → 74.75（+7.9%）；每任务成本 $1.93 → $2.17（+12.4%）。
- judge 审计（附录）：412 条被判 fortuitous 的接受轨迹中，193 条（46.8%）含 N/A 引用、192 条无最终回复（Table 12）；WebArena 记录池 Total 7,937 / Accepted 412 / Flagged 193 / N/A 345 / 无终答 192。
- 探索：No Memory 单次均值 64.3%，八次内至少一次成功 73.6%（+9.3 pp）。
- **Mind2Web 只以 Figure 3 呈现（Cross-Task / Cross-Website / Cross-Domain），逐 split 数值未获取到。**

**勘误说明（自曝）**：批次 522–527 原稿把 81.5→88.5 等值误标为「Mind2Web」，实为 SWE-bench Verified Table 2；原稿「SWE-bench 主表数值丢列未获取到」的表述作废。以上表格与成本数字均已逐字回原文核对，替换后有效。
"""
body = ENT.replace("\r\n", "\n")
stamp = time.strftime("%Y%m%d_%H%M%S")
bak = ARC + ".bak_%s_pre528" % stamp
shutil.copy2(ARC, bak)
before = io.open(ARC, encoding="utf-8").read()
b_lines = before.count("\n") + 1
with io.open(ARC, "a", encoding="utf-8", newline="\n") as f:
    f.write("\n\n---\n\n" + body)
after = io.open(ARC, encoding="utf-8").read()
print("ARC=%s" % os.path.basename(ARC))
print("LINES %d -> %d (delta=%d)" % (b_lines, after.count("\n") + 1, after.count("\n") + 1 - b_lines))
print("BYTES=%d" % os.path.getsize(ARC))
print("BAK=%s" % os.path.basename(bak))
print("HAS528=%s" % ("### 528." in after))
print("HAS_TITLE=%s" % ("Capturing the calendering U-shape" in after))
print("N528=%d" % after.count("### 528."))
