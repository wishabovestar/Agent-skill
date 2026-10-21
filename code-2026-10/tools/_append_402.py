#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 SkillOpt 归档进 CLI 论文库（编号 #402）。"""
import io
import os
import shutil
import time

A = r'D:/hermes/analysis/PAPER_ARCHIVE_agent_memory_swarm_2026-10.md'
t = io.open(A, encoding='utf-8').read()

ENTRY = """
### 402. yang2026skillopt →《SkillOpt: Executive Strategy for Self-Evolving Agent Skills》 — **15 作者**：**Yifan Yang** · **Ziyang Gong** · **Weiquan Huang** · **Qihao Yang** · **Ziwei Zhou** · **Zisu Huang** · **Yan Li** · **Xuemei Gao** · **Qi Dai** · **Bei Liu** · **Kai Qiu** · **Yuqing Yang** · **Dongdong Chen** · **Xue Yang** · **Chong Luo**（¹Microsoft ²上海交大 ³同济 ⁴复旦；∗共同一作 ‡通讯）｜⭐ **2026-05-22**｜**arXiv `2605.23904v1` [cs.AI]**｜代码 `https://aka.ms/SkillOpt` → `microsoft.github.io/SkillOpt/`（HTTP 200 实测）｜源：`arxiv.org/html/2605.23904v1`（**正文 97,909 字符**，全文级）｜**venue 未标注**

**一句话**：把 agent 的技能文档当成**冻结模型的可训练外部状态**，用一整套优化工具（学习率/调度/验证闸/拒绝缓冲）去"训练"它 —— 而不是手写或松散自修订。

**方法骨架**：
- **前向 = Rollout 证据**：当前技能在 `D_tr` 上跑批次，记录轨迹/tool calls/verifier 反馈
- **反向 = Minibatch 反思**：先把**失败与成功分开**再各自分小批（单条轨迹只会产生"轶事式"修补）；失败批提纠错规则、成功批保已有行为；**分层合并且失败优先**
- **有界文本更新**：学习率类比 = **编辑预算 `L_t`**，按预期效用排序后取 top-`L_t`；**cosine 为默认调度**；支持 patch / rewrite 两模式；步级编辑**不能覆盖受保护的 slow-update 字段**
- **验证闸 + 拒绝编辑缓冲**：候选技能须在 `D_sel` 上**严格提升**才被接受；被拒编辑连同**分数跌幅**进缓冲，供后续反思避免重犯 ⇒ 把自修订变成 **propose-and-test**
- **Epoch 级 slow/meta 更新** + **harness 无关部署**（只导出 `best_skill.md`，**部署零推理开销**）
- 超参：4 epochs · rollout batch 40 · reflection minibatch 8 · 文本学习率 4 · cosine 最小 2 · slow update 采 20 例

**关键数字**（原文实测值）：
| 指标 | 值 |
|:--|:--|
| best-or-tied | **52 / 52**（**已评**格子；6 基准 × 7 模型 × 3 harness 理论 126 格） |
| 7 直聊模型平均提升 | **≈ +17.6** 分 |
| GPT-5.5（直聊/Codex/Claude Code） | **+23.5 / +24.8 / +19.1** |
| per-cell oracle 差 | SkillOpt **82.3** vs oracle **76.9** ⇒ **+5.4** |

逐格（GPT-5.5 直聊 no-skill→SkillOpt）：Spreadsheet **41.8→80.7 (+38.9)**｜OfficeQA **33.1→72.1 (+39.0)**｜LiveMath **37.6→66.9 (+29.3)**（GEPA 仅 +5.6）｜ALFWorld **83.6→95.5 (+11.9)**｜DocVQA **78.8→91.2 (+12.4)**｜SearchQA **77.7→87.3 (+9.6)**

**原文自曝负结果**：GPT-5.4-mini ALFWorld 上**人类手写技能 = −16.4 分**（手写反而有害）。

**局限（原文 Appendix B 四条，非推断）**：①**依赖自动验证信号**（须有 scored trajectories + held-out 选择集；开放式/主观领域需更强人工或模型评估）②训练期额外 rollout 与优化器调用成本（**一次性任务未必划算**）③**只优化单个技能**，不长技能库 ④会编码训练分布特有启发式，跨域迁移前须严格 held-out 评估。

**⭐ 校准评价（不附和）**：
- **最扎实的是 +5.4 的 per-cell oracle 差**（对六法逐格取最优再被超越）—— 比"平均提升"抗打。
- ⚠️「**52/52 全胜**」口径偏松：理论 126 格只评 52（~41%），"best **or tied**" 把并列算赢，且附录 C 承认 **EvoSkill 只在有匹配完成运行处纳入**、未对齐协议项标 `–` ⇒ **基线覆盖不均**。
- ⚠️「平均 **+17.6**」是**跨不同 headroom 的平均绝对百分点**（no-skill 基数从 14.7 到 83.6）⇒ 不宜单独引用。
- ⚠️ 打的多是**通用 prompt 优化器**（TextGrad/GEPA），非技能专用方法，**方向性有利**。
- ⚠️ 全篇**未见误差棒/置信区间**；在 ±1.5 抖动带与 4 epoch 下，+5.4 的边际优势需区间才定论。

**相关性**：与 RSI / 技能演化 / 记忆巩固**高度相关**；可借鉴的具体机制 = ①有界编辑预算 ②拒绝编辑缓冲 ③失败优先分层合并 ④受保护 slow-update 字段。**但必要条件（干净标量验证器）在用户多数场景（记忆巩固/DFT/爬虫）并不具备** ⇒ 直接移植受限。

**卡片**：`D:/hermes/analysis/paper_deepread/skillopt/card.md`（9,589 B）· 全文 `skillopt_full.txt`（100,924 B）

**来源**：🟢 亲验 = 抓取字节数与代码链接 HTTP 200；🟡 引文 = 方法/数字/局限（转自 HTML 全文，含 `<math>` alttext 还原）；🔴 推断 = 校准评价与相关性判断。

"""

# 追加到"本区统计"之前，保持统计段在末尾
marker = '\n## 本区统计（批次 2026-10-15 · 续）'
if marker in t:
    t2 = t.replace(marker, ENTRY + marker, 1)
else:
    t2 = t.rstrip('\r\n') + '\n' + ENTRY

ts = time.strftime('%Y%m%d_%H%M%S')
shutil.copy2(A, f'{A}.bak_before_402_{ts}')
io.open(A, 'w', encoding='utf-8').write(t2)
print(f'  已追加 #402 · {len(t)} -> {len(t2)} 字符')
print(f'  备份: {os.path.basename(A)}.bak_before_402_{ts}')
