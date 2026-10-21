#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 ReHarness（arXiv 2610.12668v1）归档进 CLI 论文库（编号 #403）。"""
import io
import os
import shutil
import time

A = r'D:/hermes/analysis/PAPER_ARCHIVE_agent_memory_swarm_2026-10.md'
t = io.open(A, encoding='utf-8').read()

ENTRY = """
### 403. xiao2026reharness →《Recurrent Harness for Agentic Continual Learning》 — **7 作者**：**Yuxin Xiao**（MIT；实习于 Meta MRS Research）· **Zhiyun Lu** · **Jianyu Wang** · **Yangtian Zhang**（Yale）· **Yang Song** · **Qifan Wang** · **Bailin Wang**（后五者 Meta MRS Research）｜⭐ **2026-10-08**｜**arXiv `2610.12668v1` [cs.LG; cs.AI; cs.CL]**｜代码/项目页：**未获取到**（抽取文本中未见）｜源：`arxiv.org/html/2610.12668v1`（**正文 78,402 字符**，全文级含 Appendix）｜**venue 未标注**

**一句话**：把 agent harness 从「只前向演化」改成**递归** —— 每条实例结束后用刚产生的轨迹当反馈，**回头修订**当初为该实例检索到的那批 reflection，修订结果**只用在下一条实例**上；不需要 replay、不需要验证集、不需要梯度。

**问题（原文陈述）**：现有 harness 要么**只靠前向信息流**演化状态，要么依赖**额外 replay / validation 数据**做优化；严格在线流式协议下三约束——① 每实例只被观测一次 ② 无验证集 ③ 前沿 API agent 不暴露参数。后果 = 写进 harness 的 reflection **很少按「后续是否管用」更新** ⇒ 过泛化经验长期滞留、被反复检索、反复误导（Fig.1a 玩具例：「put larger numbers first」在升序查询里继续误导，**即便随后写入新 reflection 旧条目仍在**）。

**方法骨架**：
- **状态** `h_t = {R_i}`；三角色 **πD 决策 / πM 写入 / πR 修订**
- **① Forward Read**：`I_t = Retrieval(x_t, h_t, k)` → πD 出 `y_t` → 环境给 `r_t` ⇒ `τ_t = (x_t, y_t, r_t)`
- **② Backward Revision**：`R_i′ = π_R(R_i, τ_i; τ_t)` —— 用**该 reflection 的源轨迹 τ_i** 加上**它在当前 τ_t 上的下游有效性**改写它；**新内容必须 grounded 在 τ_i**（防泄漏）；τ_t 只当有效性反馈。替换被检索项、保留未检索项 ⇒ `h_t′`
- **③ Forward Write**：`R_t = π_M(τ_t, {R_i′})`，修订后的 reflections 当 **demonstrations**、并补互补视角；`h_{t+1} = h_t′ ⊕ R_t`
- 核心反问：*what information could have been captured differently in the harness state*
- 设定：**3 基准** CL-Bench（6 任务 / 12–120 多轮）· MemoryBench（5 任务 / 17–47 单轮 / GPT-5.6-Sol 评）· MemoryArena（5 域 / 20–270 任务 / 每任务 2–16 依赖实例）× **3 backbone** Claude Opus 4.8 / GPT-5.5 / Gemini 3.7 Flash；检索统一 **Qwen3-Embedding-8B** top-5；**每设定 3 次独立 stream rollout**；7 基线（Mem0/RBank/DoT/ACE/GEPA-Online/Full Raw/Top-K Raw）；指标 = 归一化增益 `(r_m − r_stateless)/(r_max − r_stateless)`

**关键数字**（★ 本人从原文直接读出复核，非子代理自报）：
| 指标 | 值 |
|:--|:--|
| Table 1 平均 | **ReHarness 0.240** > Top-K Raw 0.168 > Full Raw 0.164 > Mem0 0.131 > GEPA-Online 0.092 > DoT 0.071 > ACE 0.043 > RBank 0.034 |
| ReHarness 逐格 | CL-Bench `0.217★/0.317★/**0.233**`｜MemoryBench `0.160★/0.096★/0.064★`｜MemoryArena `0.305★/0.358★/0.408★`（★=加粗第一或并列；**唯一未加粗 = CL-Bench·Gemini 0.233 < Full Raw 0.234★**）|
| 显著性 | vs 全基线 `p_adj < 0.05`；**vs Top-K Raw 0.039、vs Full Raw 0.043**（双侧配对 Wilcoxon + Bonferroni）|
| Token（CL-Bench 全任务·Claude·单 rollout） | **41.57M**（37.19 in + 4.38 out）vs Top-K Raw 52.66M（1.3×）vs Full Raw 142.12M（3.4×）|
| **API 成本** | Top-K Raw **$85** ＜ ReHarness **$254** ＜ Full Raw **$314** ⇒ **省 token ≠ 省钱** |
| Source-grounding（Table 2，**仅 CL-Bench**） | grounded **>95%** / leakage **0.8–2.1%** / unsupported **0.5–2.6%**；每轮修订 grounding 至多 −0.3% |
| Counterfactual replay（Table 3） | **0.335** vs ReHarness 0.217 vs 无修订 0.144 ⇒ **论文自报的最大负结果** |
| 消融（去掉 `{R_i′}` 当 demos） | 0.217 → **0.191** |
| Stability / Plasticity（Table 4） | **0.015 / 0.241**（Full Raw 0.010/0.232、Top-K 0.003/0.205）|

**原文自曝负结果/局限**：① **exploitable poker 仅边际增益**（reward 与策略质量弱耦合 ⇒ 反馈是噪声）② 仍需保存原始轨迹供未来修订（存储开销）③ 只能在文本状态空间做后向反馈，不能梯度更新/验证集选择 ④ §4.1 `no repeated trials` 与 `three rollouts` 措辞张力未澄清。

**⭐ 校准评价（不附和）**：
- ⚠️ **「consistently outperforms」被自家 Table 1 推翻**：CL-Bench·Gemini 0.233 < Full Raw 0.234；「first or **tied**」把并列算赢（MemoryArena·GPT 同为 0.358）⇒ 属**过度声明**。
- ⚠️ **省 token ≠ 省钱**：总 token 少 21% 但**贵 3 倍**（$254 vs $85，输出 token 4.38M ≈ Top-K 的 9.5×）；§1「roughly one-third as many tokens」**未限定比较对象**。
- ⚠️ **效应量小、显著性贴边**：对最强 raw 基线仅 **+0.026**（0.217 vs 0.191）；`p_adj` 0.039/0.043 紧贴 0.05。
- ⚠️ **不确定性呈现不足**：**3 次 rollout**、**主表无误差棒**（`±` 只在附录 Table 5/6/7），检验观测数与 CI 未报。
- ⚠️ **缺 placebo / 等算力对照**：每实例多 1 次 reflection + k 次 revision 调用 ⇒ **无法排除增益来自「多调用」本身**。
- ⚠️ **消融覆盖窄**：组件消融只在 CL-Bench+Claude 单设定；检索器/多轮次数/grounding 约束消融**未报告**。
- ⚠️ **附录沉负格**：正文一句「leads or remains close to the best on most tasks」带过，附录有 Gemini Sales **−0.141±0.024**、Claude Cohort −0.019 等。
- ✅ 最扎实的是**消融链**（去 demos ⇒ 0.191）与 **grounded 约束的量化**（>95% grounded / leakage <3%），比「平均增益」抗打。

**相关性**：与**记忆线直接相关** —— 这是「**写完之后按效果回修**」的形式化，正对 MemOS/EverOS「写入即凝固、不再回头改」的短板；可与 **#402 SkillOpt** 互补（SkillOpt 有验证闸无 grounded；ReHarness 有 grounded 无验证闸 ⇒ 合起来 = 修订须**有据 + 过闸**）。可借鉴三机制：① τ_t 只当**有效性反馈**而非新知识 ② grounded + leakage/unsupported **量化闸** ③ **counterfactual replay 当机制有效性验证实验**。落地障碍：需「每实例有 reward + 可回取 τ_i」，用户多数场景缺干净标量 reward ⇒ 先做离线重放式验证更现实。

**卡片**：`D:/hermes/analysis/paper_deepread/reharness/card.md`（9,762 B）· 全文 `D:/hermes/analysis/papers/2610.12668v1.txt`（78,402 字符）

**来源**：🟢 亲验 = 正文 78,402 字符 + Table 1 全部 8×9 格与加粗标记 + Table 3/4 + token/$ + grounding 三率（本人直读）；🟡 引文 = 机制/设定/局限（转自 HTML 全文）；🔴 推断 = 校准评价 7 条与相关性判断。

"""

# 追加到"本区统计"之前，保持统计段在末尾
marker = '\n## 本区统计（批次 2026-10-15 · 续）'
if marker in t:
    t2 = t.replace(marker, ENTRY + marker, 1)
else:
    t2 = t.rstrip('\r\n') + '\n' + ENTRY

ts = time.strftime('%Y%m%d_%H%M%S')
shutil.copy2(A, f'{A}.bak_before_403_{ts}')
io.open(A, 'w', encoding='utf-8').write(t2)
print(f'  已追加 #403 · {len(t)} -> {len(t2)} 字符')
print(f'  备份: {os.path.basename(A)}.bak_before_403_{ts}')
