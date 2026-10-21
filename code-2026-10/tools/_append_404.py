#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 RSIPO（arXiv 2610.15772v1）归档进 CLI 论文库（编号 #404）。"""
import io
import os
import shutil
import time

A = r'D:/hermes/analysis/PAPER_ARCHIVE_agent_memory_swarm_2026-10.md'
t = io.open(A, encoding='utf-8').read()

ENTRY = """
### 404. zhang2026rsipo →《RSIPO: Recursive Self-Improving Policy Optimization for Agentic Reinforcement Learning via Skill-Policy Co-Evolution》 — **10 作者**：**Fan Zhang** · **Hao Wu** · **Jinyang Wu** · **Hongyu Qu** · **Zheng Lian** · **Xiao Luo** · **Yefeng Zheng** · **Bo Zhang** · **Haoxuan Li** · **Pheng-Ann Heng**（原文脚注 `*` 同等贡献 / `†` 通讯）｜⭐ **2026-10-11**｜**arXiv `2610.15772v1` [cs.LG]**｜✅ **代码仓实证存在**：`https://github.com/zfkarl/RSIPO`（**HTTP 200 / 442,762 B / `<title>GitHub - zfkarl/RSIPO`**，含 `README.md`·`LICENSE`·`requirements.txt` 痕迹）｜源：`arxiv.org/html/2610.15772v1`（HTML 460,972 B → **正文 61,013 字符**，全文级含 Appendix，2,524 行）｜**venue 未标注**｜引用数 **0**（OpenAlex `W7221771183` 独立复现）｜⚠️ 单位上标在 HTML 去标签后丢失：文中出现 THU · NUS · Tongji University · UW-Madison · Westlake University · CUHK · Shanghai AI Laboratory · PKU，**作者↔单位一对一映射不可得**

**一句话**：在 agentic RL 的 **RLVR + OPSD 混合框架**上补两个被忽视的环节 —— **①技能生成须 on-policy 演化、②教师监督不可盲信**：用「**轨迹回放执行检查**」把自生成技能归因成**单元级增益**（一半 rollout 当证据、一半当对照），该增益**①** 直接当策略写技能的奖励、**②** 经**经验贝叶斯收缩**映射成**信任系数 ω** 去加权 OPSD；噪声大时 `ω→1` 自动退化为标准 OPSD。

**问题（原文陈述）**：① **off-policy drift** —— 现有混合法技能来自静态外部库或**预先 off-policy 训好的生成器** ⇒ 策略越练越强、技能生成不同步。实证（Fig.2a，7B/ALFWorld）：训练技能生成器的 SFT 数据**仅 0.25% 轨迹成功**（base 仅 **11.0%** 步骤符合动作格式），RL 中 rollout 成功率迅速 **>80%**；SFT 里 **86.8%** 的「技能」只讲动作格式/语法，而**前 10 个 RL 步**已 **99.7%** 动作合法 ⇒ 待总结轨迹从「几乎全失败」变成「以成功为主」。② **教师不可靠** —— OPSD 隐含假设「带技能的教师更可靠」但**有技能 ≠ 更好**（Fig.2b/c）：教师仅在 **5.5%–22.4%** 任务上不如学生，优势**集中在学生 4 次 rollout 中成功 1–3 次的任务**，学生 0 或 4 次成功时两者比例相近（**16.0% vs 13.6%** / **6.9% vs 5.5%**）；RL 前 15 步教师**劣于**学生的任务反而更多（**22.9% vs 15.0%**），其后仍持续 **4%–11%**。

**方法骨架**（§3 逐式亲读）：
- **环境**：≤ `T_max` 轮、**可验证二元奖励** `R(τ)∈{0,1}`；每任务 `G` 条轨迹 + GRPO 组内归一化；`L_RLVR = L_PPO + λ_KL·L_KL`
- **技能增强教师**（沿用 SEED）：策略自己把轨迹摘要成技能 `s`；教师 = **同一策略插入技能** `π_T(·|c_t)=π_θ(·|c_t ⊕ s)`；门控蒸馏 `ℓ=g_{t,j}(log π_T − log π_θ)`、`g=σ(β(log π_T − sg[log π_θ]))`
- **执行检查**：`G` 条 rollout **先于任何结果被观测**就**均匀随机**劈成**证据集 ℰₓ / 对照集 𝒞ₓ**（等大小）→ 从 ℰₓ 选一条（优先成功）让策略**重写技能 sₓ** → 技能合法则教师带技能**从同一初始态回放 K 次**
  - 效用 `u(τ)=I[R(τ)=1]·(1−α·T(τ)/T_max)`；**回放增益** `Δₓ=(1/K)Σu(τ̃_k) − (1/|𝒞ₓ|)Σ_{𝒞ₓ}u(τ)`
  - **噪声方差** `vₓ=Σ_{a∈{rep,ctl}} ũ_a(1−ũ_a)/n_a`，`ũ_a` 为 Laplace 平滑 `(n_a ū_a+1)/(n_a+2)`
- **类型池化 + 经验贝叶斯**：同类型 `c`（ALFWorld 任务类 / search 源数据集）维护 `m_c←(1−η)m_c+η(Δ̄, Δ̄², v̄, 1)` ⇒ 类型均值 `Δ̄_c` 与**任务间方差** `σ̂²_c=max(0, m^{(2)}/m^{(0)} − Δ̄_c² − m^{(v)}/m^{(0)})`（**总方差减噪声方差**）⇒ `ĝₓ=wₓΔₓ+(1−wₓ)Δ̄_c`，`wₓ=σ̂²_c/(σ̂²_c+vₓ)`；无有效回放退化为先验 `ĝₓ=Δ̄_c`
- **① 奖励技能生成**：`rₓ=Δₓ−Δ̄_{c(x)}`（**中心化、刻意不收缩**——作者理由：策略梯度信号应无偏，收缩会在「任务间方差分不出来」时压没全部奖励）；非法技能 `rₓ=−ρ`、**无法复现初始态**的任务 `rₓ=0`；search **不罚**非法技能（ρ=0）但对合法输出格式 token 给 **0.05**；`L_skill=−(1/|X|)Σ rₓ·ℓ̄ₓ`（reward-weighted log-likelihood，仅技能串 token 计权），其梯度与**最后一个 PPO mini-batch** 合并成一次优化器步
- **② 校准信任**：`ωₓ=clip(1+κ·ĝₓ, 0, ω_max)`、`L_OPSD(ω)=(1/N)ΣᵢΣ_{t,j} ω_{x(i)}ℓ_{t,j}` ⇒ `L=L_RLVR+λ_OPSD·L_OPSD(ω)+L_skill`；`κ=2, ω_max=2` ⇒ `ĝ≤−0.5` **关蒸馏**、`ĝ≥0.5` **加倍**；**用收缩后的 `ĝ` 而非 `Δ`**（逐任务噪声会直接扭曲损失权重）；`ω≡1` 即原版 OPSD
- **冷启动**：沿用 SEED，先用外部 LLM（**GLM-5.2**）为 base model 自身轨迹标注的 skill 对做 SFT；**测试时一律不给技能**

**规模**：**ALFWorld**（成功率）+ **7 个 search 数据集**（exact-match：NQ/TriviaQA/PopQA 单跳 + HotpotQA/2WikiMultiHopQA/MuSiQue/Bamboogle 多跳）× **3 backbone**（Qwen2.5-3B / Qwen2.5-7B / Qwen3-1.7B）；**13 基线**（Vanilla · Skill-Prompt* · GRPO · Skill-GRPO · Skill-GRPO* · OPSD · GRPO+OPSD · Skill-SD · RLSD · SDAR · StepOPSD · OPID · **SEED**；`*`=测试时带技能，其余含 RSIPO **测试时无技能**）；**150 步**、`G=8`、**16 任务/步**（ALFWorld）或 **128**（search）、lr `1e-6`、KL **0.01**（ALFWorld）/**0.001**（search）、`λ_OPSD=0.01`、`β=5`、`K=4`、`α=0.5`、`η=0.1`、`ρ=0.2`；**8 × NVIDIA H20**（**未给 GPU-hour/token/$**）

**关键数字**（★ 本人从**原文表格**直接读出，非子代理自报）：
| 方法 | ALFWorld 平均（3B / 7B / 1.7B） |
|:--|:--|
| Vanilla | 21.9 / 12.5 / 12.5 |
| OPID（最强非 SEED 基线） | 84.3 / 90.0 / 58.9 |
| **SEED**（原文称 strongest prior） | **91.8 / 96.1 / 92.0** |
| GRPO | 75.0 / 81.2 / 46.1 |
| GRPO+OPSD | 81.2 / 80.4 / 32.0 |
| **RSIPO** | **95.7 / 98.6 / 95.0** |
| RSIPO−SEED | **+3.9 / +2.5 / +3.0** |
| RSIPO−GRPO | +20.7 / +17.4 / +48.9 |
| RSIPO−GRPO+OPSD | +14.5 / +18.2 / +63.0 |

- **search 7 数据集平均**：RSIPO **50.8**（7B，**第一**）· **42.6**（1.7B，第一）· **45.3**（3B，**第二，低于 SEED 45.7 达 0.4**）；SEED = 48.6 / 42.2 / **45.7**；GRPO = 42.0 / 40.8 / 36.4；RSIPO 相对 GRPO **+8.9 / +8.8 / +1.8**
- **vs 带技能基线**：7B 上超 Skill-GRPO* **+10.3**（ALFWorld）/ **+3.3**（search）
- **Fig.4b 累积消融**（ALFWorld/3B）：base **21.9** → 仅 OPSD **28.1** → GRPO **75.0** → GRPO+OPSD **81.2** → +SFT 初始化 **86.4** → **+动态信任 3.6** → **+技能演化 5.6** → **95.7**（加总 95.6，差 0.1 属舍入）；**去掉任一组件代价 3.7–5.7**
- **训练动力学**（Fig.4a/3B）：成功率 **63%→>90%**（ALFWorld）、**32%→53%**（search）；动态信任 ALFWorld **20 步内 >1.1**、search **≈1**
- **技能演化**（Fig.5/7B）：Procedure/Format/Recovery 三类，早期 SFT 技能多为 Format·Recovery 且**平均回放增益为负**，末 45 步 **Procedure >94%**、增益转正

**原文自曝负结果/局限**：① **额外 rollout 抬高训练成本** ⇒ 效果与算力权衡（**无数字**）② **依赖可重置环境**（模拟器/离线检索），不可重置场景（实网交互）留作未来工作 ③ **GRPO+OPSD 在 7B、1.7B 上不如 GRPO**（ALFWorld 80.4<81.2、32.0<46.1）⇒ 反证「无条件信任教师」有害 ④ search 增益显著小于 ALFWorld，作者归因「更依赖检索证据而非程序性技能」，机制证据 = 该场景信任值≈1。

**⭐ 校准评价（不附和）**：
- ⚠️ **摘要「outperforms all the compared baseline approaches」是过度声明**：**3B 的 search 平均 RSIPO 45.3 < SEED 45.7**，而正文 §4.2 自己承认「ranks second, only 0.4% below SEED」⇒ 摘要与正文冲突。
- ⚠️ **search 优势在 2/3 backbone 上属噪声级**：7B **+2.2**、1.7B **+0.4**、3B **−0.4**；**1.7B 的 +0.4 尤其不可当结论** —— 7 个数据集中 RSIPO **3 个不如 SEED**（NQ 40.0 vs 42.0 / Triv 58.5 vs 58.9 / Hotp 35.2 vs 36.9）、1 并列（Bam 64.9）、3 领先。
- ⚠️ **逐数据集第一也不成立**：7B 上 **NQ 46.8 < OPID 48.8 / SEED 47.0**、**HotpotQA 45.3 < SDAR 48.4 / OPID 46.1 / RLSD 45.5**（平均第一主要靠 Triv 67.8、2Wk 52.1、Bam 73.8）；3B 上 **4/7 数据集不如 SEED**（NQ 39.0 vs 44.3 差距最大）。
- ⚠️ **「GRPO+OPSD 不如 GRPO」只对 ALFWorld 成立**：search 上 7B **47.0 > 42.0**、1.7B **42.2 > 40.8**（加 OPSD 反而涨）；原文该句**未限定基准**，字面读被表格推翻。
- ⚠️ **不确定性与重复性完全缺位**：全文含附录**未见**种子 / 重复次数 / 误差棒 / 置信区间，主表与消融只有**点值** ⇒ 2.5、3.9、3.0 这类差距**是否超出 run-to-run 波动无从判断**。
- ⚠️ **成本只有定性**：唯一成本表述是 Limitation ① 一句话；按设定推算 **G=8 与 GRPO 相同、RSIPO 另付每任务 1 次技能重写 + K=4 次教师回放 ⇒ 净增约 +50% rollout 量级 + 1 次 LLM 调用/任务**（推断），该代价未与收益并列。
- ⚠️ **消融面窄 + 基线可复现性未交代**：Fig.4b 只在**单一设定**（ALFWorld×3B）；`K/η/κ/ω_max/ρ`、证据-对照对半等超参敏感性**概未报告**；13 基线只给介绍，**未说明数字是自跑还是引自原文**，而对照公平性是全部论断的前提。
- ✅ **最扎实**：① **Fig.2 动机分析是真测出来的**（0.25%/11.0%/86.8%/99.7%/22.9% vs 15.0% 全来自自家实验）② **回放检查的统计设计干净**（先于结果劈半、Laplace 平滑、方差项显式扣噪、EB 用 `ĝ` 而非 `Δ`、策略梯度侧刻意不收缩并给出理由）③ **优雅退化可证伪**（`ω≡1` 数学上回到原版 OPSD，search 实测信任≈1）④ 消融链**单调自洽**。

**相关性**：与 **#403 ReHarness** 同属「自我改进闭环」但机制正交 —— ReHarness = **LLM 修订 + grounded/leakage 量化**（无执行回放）；RSIPO = **执行回放归因 + 经验贝叶斯收缩**（无文本 grounded 约束）⇒ 合起来 = 记忆线缺的两半「**回放验证**」+「**有据修订**」。可借三件：① **证据/对照先于结果劈半**（与我 `probe_memos_miss.py` 的 M0/M1 单变量重放同构，但 RSIPO 把它做进训练循环并估方差）② **EB 收缩 `ĝ=wΔ+(1−w)Δ̄` 与 `σ̂²=总方差−噪声方差`** —— 正是我审计铁律「方差≥差距 ⇒ 降级为定位而非排名」的形式化，可直接用于记忆条目归因（我的样本也是 K=4 量级）③ **信任系数 graceful degradation** 与我闸的 **fail-open（log 默认/suppress 才拦）** 同哲学。**同构的病**：论文诊断的「生成器 off-policy drift」与我已定案的 **MemOS 双写者不一致**（捕获嵌 `user_text`、修复嵌 `summary`）是同一类**产消源漂移** ⇒ 持久修法不应只对齐文本来源，还应让**写入侧效用由消费侧结果反馈**。**落地障碍**：RSIPO 硬依赖**可重置环境 + 二元可验证奖励**，我的记忆场景两者皆无 ⇒ 移植的是**统计设计**，验证走离线重放。

**卡片**：`D:/hermes/analysis/paper_deepread/rsipo/card.md`（16,752 B）· 全文 `D:/hermes/analysis/papers/2610.15772v1.txt`（61,013 字符）· 元数据 `papers/2610.15772v1.meta.json`

**来源**：🟢 亲验 = 正文 61,013 字符 + 摘要逐字（含「outperforms all the compared baseline approaches」、98.6%/2.5%/17.4%）+ **Table 1（7B+1.7B）与 Table 3（3B）全部 13 基线逐格数值** + SEED/RSIPO 三 backbone 双基准平均 + §3 全部公式与超参 + §4.2/4.3 与 Limitations 全文 + Fig.2 动机数字串 + **代码仓 HTTP 200/442,762 B/title/文件痕迹** + OpenAlex `W7221771183` `cited_by_count=0`（均本人直读）；🟡 引文 = 基线一句话描述、GLM-5.2 标注、`*` 含义、Appendix A；🔴 推断 = 校准评价 9 条、相关性 4 条、「净增约 +50% rollout」估算。

"""

# 追加到"本区统计"之前，保持统计段在末尾（与 #403 同法）
marker = '\n## 本区统计（批次 2026-10-15 · 续）'
if marker in t:
    t2 = t.replace(marker, ENTRY + marker, 1)
else:
    t2 = t.rstrip('\r\n') + '\n' + ENTRY

ts = time.strftime('%Y%m%d_%H%M%S')
shutil.copy2(A, f'{A}.bak_before_404_{ts}')
io.open(A, 'w', encoding='utf-8').write(t2)
print(f'  已追加 #404 · {len(t)} -> {len(t2)} 字符')
print(f'  备份: {os.path.basename(A)}.bak_before_404_{ts}')
