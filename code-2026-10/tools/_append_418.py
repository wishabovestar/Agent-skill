#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把单篇深读 EHRBench（2605.30637v1）归档进 CLI 论文库（编号 #418）。

纪律（同 #403/#404/#405）：插在「## 本区统计（批次 2026-10-15 · 续）」之前 +
时间戳备份 + 读回验证。所有数字均来自本人在 papers/2605.30637v1.txt 的逐行亲读与算术复核，
未采信任何子代理自报；原文没有的（医生一致性验证）写「原文没有」，未取到的写「未获取到」。
"""
import io
import os
import shutil
import time

A = r'D:/hermes/analysis/PAPER_ARCHIVE_agent_memory_swarm_2026-10.md'
t = io.open(A, encoding='utf-8').read()

SECTION = "## 单篇深读（续 · 2026-10-16）"

ENTRY = """
### 418. [临床决策基准 · EHR 接地] EHRBench: An Automated and Reliable EHR-based Benchmark for Clinical Decision Making with LLMs（2605.30637v1 · 2026-05-28 · cs.AI）— Emory University + Stanford University｜⭐ **2026-10-16**
- **id**: 2605.30637（v1；arXiv XML `comment`/`journal_ref`/`doi` **三字段全空**；外网检索称 **KDD 2026** / DOI `10.1145/3770855.3817571` —— 🟡 非 arXiv 原文陈述，未二次坐实）
- **source_obtained**: 全文（`arxiv.org/html/2605.30637v1`，LaTeXML ≈868 KB → 去标签正文 **185,689 B** → `papers/2605.30637v1.txt`，sha256 前16 = `5564056e…`；含 Table 1/3/4/12/17 与 Appendix A–L，备源 ar5iv + Emory PDF 已抓未用）
- **confidence**: high
- **问题**: 临床决策（CDM）是真实工作流核心、LLM 越来越多被用于支持它，但其在**真实临床决策任务上的可靠性"仍未被充分理解"**；直接用原始结构化 EHR 造基准有难点（关系抽取需临床推理、易幻觉），且理想基准须「automated yet reliable」同时保规模与质量。作者自述定位：**首个**由原始结构化 EHR 轨迹直接构建 + LLM 生成模板 + 强制系统化校验的基准。
- **方法**: 「**EHR → 医疗 LLM → 生物医学 KB**」三段交互管线。①**Stage 1**：**HuatuoGPT-o1-8B** 在严格 JSON 约束下从病历抽临床关系三元组 `R_k=(x_k,r_k,y_k)`（如 `(Hyperglycemia, Treat-with, Insulin)`）+ 辅助上下文事件 `C_k`（**强制与 R_k 无词法/语义重叠**）；②**Stage 2**：事件经 **UMLS API** 解到 CUI，再向 **SemMedDB**（PubMed 关系）取证据，**三条件全满足才保留** —— 逐字为 **Positive support** / **No negative evidence** / **No conflicting background evidence**（相对背景概念集 `C_k` 无矛盾）；③**Stage 3/4**：JSON schema 补全结构化属性 + **KB 过滤干扰项**（给定锚概念与上下文下**也被 KB 支持**的备选剔除，保唯一答案）；④**实例化**：每模板 × 选项数 c 生成 4/5/6 选 MCQ（各 **c 个确定性变体** = 改写 + 答案位置置换）与开放题；**泄漏防护 = 只做设计约束**（禁词 + 题干/选项非重叠），另做 JSON/结构校验。**评测**：模型只见自然语言输入，答案/选项/证据/关系**全部扣留**；MCQ 用 ACC，OEQ 用 Coverage/ROUGE/BERTScore；主用 **PyHealth** 预处理，遇以 stay 为单位（预后任务 = 同患者相邻两次 encounter 对）。
- **关键数字**: 三源 **MIMIC-III v1.4** 38,597 患者/53,423 住院（2001–2012）· **MIMIC-IV v3.1** 364,627/546,028（2008–2022）· **PROMOTE**（Emory 私有，IRB `2025P010425`）18,561 患者/912,706 记录（2012–2021）；就诊纳入门槛 **≥5 条诊断 + ≥3 条治疗事件**；**每源每任务最多前 10,000 实例**（上限 90,000，算术复核）；构建漏斗 **465,748 候选关系 → 62,786 KB 校验模板（留存率 13.5% 明报）→ 960,067 题**（≈**15.29 题/模板**）；任务 治疗 **450,501** > 预后 **259,123** > 诊断 **250,443**；源 MIII **323,193** / MIV **259,089** / PRO **377,785**（**PRO 占 39.35%**）；题型 MCQ-4 250,924 / MCQ-5 301,100 / MCQ-6 345,396（⇒ OEQ **62,647**）；算力 **560 H100 GPU-hours**；评测 **31 个 LLM**，主实验固定子集 **每 任务×源×题型 前 3,000 题 ⇒ 27,000 题/模型**（另做全量集对照 Appendix H）；ICD-10-CM 码 **3,808 → 3 位截断 752**；**Table 1**（12 列 = Acc｜Rank Avg↓｜Rank SD｜Dx/Tx/Px｜MIII/MIV/PRO｜4C/5C/6C）**gpt-5.2 70.91 #1 / Rank Avg 1.69 / SD 1.10**（Px 60.59、PRO 70.70、6C 66.81）· gpt-4.1 69.43 #2 · gpt-5 69.06 #3 · llama3.3-70b 67.28 #4 · gpt-4.1-mini 66.79 #5 · qwen3-32b 66.78 #6 · glm4-32b 66.12 #7 · gpt-5-mini 66.12 #8；任务均值 **Tx 69.33% > Dx 55.02% > Px 46.67%**；源均值 58.26/57.69/55.45；选项 **4C 62.29 → 5C 56.69 → 6C 52.04**；**医学微调负结果** m1-32b-1k **63.21% < 基座 qwen2.5-32b 64.97%**；gpt-5.2 − llama3.3-70b = **3.63 pp**（原文称"缩小到 3–4 绝对点"，复算✅）；鲁棒性 `V-Std`=同题各版本准确率 SD、`V-Cons`=同题各版本预测选项完全相同的比例（Eq.14–17）；Table 12 把错误拆为 Prediction Wrong / No JSON / Output Malformed。
- **结论**: 在统一推理协议下 31 个 LLM 的分层结果与既有能力序一致（治疗最易、预后最难、数据集效应温和、**医学微调无一致增益**），据此作者称"验证了构建管线与评测协议"；并据"强模型得分高 + 选项数增加单调降分 + 公开/私有集趋势一致"主张基准可信、难度受控。产出近百万题（960,067）的自动化 + KB 校验基准，定位为避免原始病历外泄、可查的 CDM 测试台。
- **局限（原文自陈，Appendix K 四条）**: ①只用**结构化**诊断/处方/操作，**排除**人口学、生命体征、化验、影像；②每模板只用**小而定长上下文窗**，只做 encounter 级，预后任务实为**下一次就诊风险预测**（**非**校准的 time-to-event）；③**全量评测被省略**（成本/时长不可行）⇒ 只用截断子集；④KB 支持**以 recall 换 precision** ⇒ 罕见/新兴/机构特异实践可能被**系统性低估**。
- **相关性**: (a)**形态学同类** —— 本基准核心 = 「自动生成 + 独立知识源校验 + 明报留存率」，与本仓 `grounded_gate.py` / `cortexmem_write_gate`（写入必须可机械核查）同范式，只是它的 KB 是 UMLS/SemMedDB/DrugBank/PubMed；(b)**可直接引用的标尺 = 13.5% 留存率明报** —— 本仓写闸默认 `log` 只记不拦，台账应照样**明报分子分母**，否则无法判闸宽严；(c)**反面教材** —— 原文用"强模型得分高"当"管线有效"的证据属**循环论证**（`:873` 逐字 *validating the construction pipeline*），正是本仓 REPRO_AUDIT「判不复现前先证明检查器能命中已知在源数」要切断的自证闭环；(d)**可照抄做法** —— 先固定子集跑、再用全量/扩展集对拍证明子集无采样偏差（Appendix H），本仓长跑/复测应照此；(e)**同病** —— 与 STRATA/RSIPO 一样无种子/无重复/无误差棒 ⇒ 再次印证 W5 铁律（方差未知 ⇒ 只定位不排名）；(f) 作为极片热工艺从业者，其「事件 → 关系抽取 → 独立证据源筛 → 明报留存率」漏斗对我司工艺/失效知识库建设有形态参考（推断）。
- **⭐ 校准评价（本人判断，不附和）**: ①**「reliable」全部落在 KB 上，零医生/临床一致性验证** —— 全文 `physician` 仅 1 次且出现在**参考文献标题**（LLMEval-Med）⇒ reliable = 「关系有文献支持」，**不等于**「问题临床有效/难度合适/答案无争议」。②**循环论证**：用参评模型表现自证基准有效（见上 (c)），只说明"与已有能力序一致"。③**主表没有任何准确率不确定度**：`±` 0 命中、`stderr` 0、`confidence interval` 0、`seed` 1；Table 1 的 "SD." 属 **Rank 组**（是**排名均值 1.69 的 SD**，**不是**准确率误差棒）⇒ 「只差 3–4 点」无可判显著性口径。④**V-Cons 只量版本间预测是否相同、不量对错** ⇒ 高一致性可由**稳定地错**产生。⑤**泄漏只做设计约束，无任何量化泄漏检出率**（"reliable"的泄漏维度不可验证），且作者自认 KB 有 precision 优先的覆盖偏置，「覆盖广（3,808 码）」与「罕见实践被低估」张力未解。⑥**规模来自模板级组合放大**（62,786 → 960,067 = 15.29×/模板）且题源是截断子集 ⇒「近百万题」≠ 近百万病例覆盖（推断）。⑦**39.35% 的题来自私有 PROMOTE** ⇒ 该部分第三方不可复现（推断）。⑧✅**最扎实处**：三条件判据可机械判定并逐条写明；**留存率 13.5% 明报**（多数论文只报最终规模）；稀疏就诊门槛显式；**负结果照写**（医学微调无增益、Px 最难）；局限自陈具体；**算术自洽**（三套拆分皆回到 960,067，本人复算✅）；错误分解把"格式失败"与"知识失败"分开报。
- **来源**: 🟢 亲验 = 上述全部数字（本人直读 `papers/2605.30637v1.txt` 逐行 + 三套拆分/15.29×/39.35%/3.63 pp/90,000/62,647 全部机器复算；GitHub 首页 HTTP 200 / **326,971 B** / title 命中；arXiv API 读出 10 作者与 `cs.AI`）／🟡 = KDD 2026 + DOI（上一轮 web 检索）、HuatuoGPT-o1-8B/PyHealth/UMLS/SemMedDB/DrugBank/ICD 的一句话描述（转自原文）／🔴 推断 = 全部校准评价 8 条 + 相关性 6 条。
- **未获取到**（如实，未做补全）: Table 1 其余 25 行（只读 6 行完整 12 列 + 约 10 个 Overall 点值；qwen3-32b 的 Rank Avg 未读）；Table 17 逐模型 V-Std/V-Cons 数值（只取表头 + 定义）；Table 12 逐模型完整数值（只取片段）；Appendix E.5 / F / H 的具体数字（只有正文转述）；作者↔单位一对一映射（HTML 丢上标）。**医生一致性验证：原文没有（非"未取"）**。
- **本卡正文全文**：`paper_deepread/ehrbench/card.md`（15,985 B，完整版含 Table 1 六行 12 列表格、Appendix K 逐字、来源分级）

"""

marker = '## 本区统计（批次 2026-10-15 · 续）'
idx = t.rfind(marker)
if idx == -1:
    raise SystemExit('未找到插入锚点，未改动文件')
head, tail = t[:idx], t[idx:]
block = SECTION + '\n' + ENTRY
if '### 418.' in head:
    raise SystemExit('#418 已存在，未改动文件')
t2 = head + block + tail

ts = time.strftime('%Y%m%d_%H%M%S')
bak = f'{A}.bak_before_418_{ts}'
shutil.copy2(A, bak)
io.open(A, 'w', encoding='utf-8').write(t2)
print(f'  已插入 #418（含新节标题「{SECTION}」）')
print(f'  字符 {len(t)} -> {len(t2)}（+{len(t2)-len(t)}）')
print(f'  插入位置：第 {t[:idx].count(chr(10))+1} 行之前')
print(f'  备份: {os.path.basename(bak)}')
