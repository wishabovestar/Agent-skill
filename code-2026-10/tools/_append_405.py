#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「本仓器械落地」归档进 CLI 论文库（编号 #405）。

条目内容 = RSIPO(#404) 两件器械的形式化落地（EB 收缩 + 劈半对照模块）
         + MemOS 向量源持久修法（含 2×2 因果闭环）
         + L35 空壳定案指针。
纪律：#404 同法 —— 插在「## 本区统计」之前 + 时间戳备份 + 读回验证。
"""
import io
import os
import shutil
import time

A = r'D:/hermes/analysis/PAPER_ARCHIVE_agent_memory_swarm_2026-10.md'
t = io.open(A, encoding='utf-8').read()

ENTRY = """
### 405. 本仓器械（RSIPO 落地）→《EB 收缩 + 劈半对照统计模块 `eb_shrink.py` v1.0》＋《MemOS 向量源持久修法（幂等补丁 + 2×2 因果闭环）》 — 非论文条目，**承接 #404 RSIPO 的「可借三件」②**（EB 收缩 / 先于结果劈半）之落地，接本仓真实 A/B 数据（`probe_M0_baseline.log` / `probe_M1_surgery.log`，39 条，不造数据）｜⭐ **2026-10-16**｜模块 `D:/hermes/analysis/memory_ab/eb_shrink.py`（v1.0，约 440 行；CLI `selftest | audit | run | who | stats`；台账 `eb_shrink_ledger.jsonl`）｜报告 `EB_SHRINK_SPLIT_HALF_DRAFT_20261016.md`（69 行）｜状态 **端到端跑通**：selftest **21/21**、audit **5/5**、run exit 0、独立手算对拍 **3/3**

**一句话**：把 RSIPO 的「**先于结果劈半的证据/对照**」与「**经验贝叶斯收缩 `ĝ=wΔ+(1−w)Δ̄`**」抽成可复用统计模块（`split_half(items,seed)` / `shrink(Δ,σ²_noise)`），用于**判断一条真实 A/B 效应是「稳」还是「只是采样噪声」**；噪声主导时**主动拒绝产出逐项排名**（而非给假排名）。

**关键数字（本人一手核，全部来自本仓落盘日志）**：
- **数据**：M0 命中 **28/39**、M1 命中 **37/39**、`Δ̄=+0.2308`（摘要手术前后，单变量）。
- **EB 收缩（三噪声界）**：`pooled`（默认，`σ²=0.25115=p₀(1−p₀)+p₁(1−p₁)`，`p₀=0.718/p₁=0.949`）⇒ **w=0.0000**；`conservative`（σ²≡0.5）⇒ **w=0**；`mle_item`（乐观上界）⇒ **w=0.6833**（精确分数 **41/60**，`_eb_blind_check.py` 用 `Fraction` 独立复算逐位一致）。**方差分解：总 0.18219 vs 噪声 0.25115 ⇒ 信号 −0.06896 ⇒ 钳到 0。**
- **劈半对照**（seed=20261016，A=20/B=19）：halfA `Δ̄=+0.2000 CI[+0.0500,+0.4000]`（翻正 4 / 翻负 0）· halfB `Δ̄=+0.2632 CI[+0.1053,+0.4737]`（翻正 5 / 翻负 0）⇒ **两半同向为正 ⇒ 总效应稳**；逐项归因则 **w=0 ⇒ 只定位、不排名**（区间 `w∈[0.000,0.683]`）。
- **判据必须能失败**：纯噪声 200 次重复 ⇒ 均值 `w=0.0124`、**102/200 触发钳位**、p95 `w=0.0525`（不产生假排名）；已知分级信号 ⇒ top-20 **精确复原**（w=0.844）；噪声淹没信号 ⇒ w=0 且排序塌掉。
- **术语方向（易混，代码注释标死）**：RSIPO 的 `ω` 是「蒸馏信号信任系数」，噪声大 ⇒ `ω→1` 退化回原版；本模块 `w` 是「原始 Δ 的保留权重」，噪声大 ⇒ `w→0` 退化为全局均值。**方向相反、物理含义相同。**

**MemOS 向量源持久修法**（同批，源自已定案的「向量写者不一致」真 bug）：
- **两处同病点**（`memory-core.js::collectEmbeddingSlots()` trace 槽 + `capture.js:897 enqueueMissingTraceVectors()`，后者由 `retry-worker.js:38` 消费）均 **`summary` 优先**，与捕获路径 `embedder.js::summaryText`（用 `userText`）不一致 ⇒ 一律改 **`row.userText?.trim() || row.summary?.trim() || "(empty)"`**。
- **2×2 因果闭环**（真跑重嵌 + 另一进程直读 DB 复核）：**还原 buggy 代码** ⇒ 全库仅有的 2 行 `summary≠user_text`（L07/L31）嵌的是 `embed(summary)`（`cos=1.00000`，`cos(user_text)=0.67653/0.71223`）；**打补丁** ⇒ 同一 2 行翻成 `embed(user_text)`（`cos=1.00000`），两次余弦值**逐位对称** ⇒ 单变量因果坐实，非巧合。重嵌 41 槽 `updated=41`。
- **改的是 `node_modules` ⇒ npm 重装即失效** ⇒ 幂等补丁 `patch_memos_embedding_source.py`（`selftest 9/9`；`--check` 覆盖 **2 个安装点 × 2 文件 = 4 站点**，全 ORIGINAL 时 exit 1 ⇒ 判据能失败；`--apply/--revert`）+ 巡检看门狗 `memos_embed_patch_watchdog.py`（挂 Hermes cron `4dfc38e9cc85`，每 6h，no_agent；**健康时 stdout 空 ⇒ 不发通知**，失效则自动重打并出声；两腿均已真跑：健康静默 exit 0 / 打回后自动重打 4/4 复原）。

**L35 空壳定案（指针）**：非检索失败，**非 bug 不需修** —— adapter `prefetch` 的 `_is_explicit_delegation_request(query)` 命中「子代理/子任务/派发」等委派词即按设计 `return ""`；全库实测**恰 2 组/11 行**命中、**单变量因果 5/5**。报告 `L35_EMPTY_SHELL_ROOT_CAUSE_20261016.md`（74 行）。

**局限（如实）**：① 噪声只有 **2 次观测/项**（RSIPO 可在任务内以 G 条回放估噪，本仓无重复实验）⇒ 只能用 Bernoulli 池化 + 保守/乐观**区间**替代点估，**要收窄须对同 39 条跑 ≥3 次重复**。② 合成用例分布 ≠ 真实语料 ⇒ selftest 只证函数性质，**绝对数字不可移植**，真实结论只来自上列第 3 节。③ 补丁面向 **`@memtensor/memos-local-plugin` 2.0.20 的确切代码行**，**升版即需重新定位**（`--check` 会以「异常」而非「已修」出声）。

**文件**：`memory_ab/eb_shrink.py` · `memory_ab/_eb_blind_check.py`（83 行，独立手算）· `memory_ab/patch_memos_embedding_source.py`（214 行）· `hermes-data/profiles/mybot/scripts/memos_embed_patch_watchdog.py`（49 行）· `memory_ab/check_vec_origin.py`（75 行，A/B 判据）· 日志 `_eb_shrink_run.log`/`_eb_blind_check.log`/`_rebuild_fix1.log`/`_vec_origin_*.log`/`_patch_apply*.log`

**来源**：🟢 亲验 = 上文全部数字（本仓落盘日志与 `memos.db` 直读；手算经 `Fraction` 独立复算；2×2 因果经另一进程直读 DB 复核）；🔴 推断 = 「要收窄区间须 ≥3 次重复」之因果归因、「升版需重新定位」之风险判断。

"""

# 追加到"本区统计"之前，保持统计段在末尾（与 #403/#404 同法）
marker = '\n## 本区统计（批次 2026-10-15 · 续）'
if marker in t:
    t2 = t.replace(marker, ENTRY + marker, 1)
else:
    t2 = t.rstrip('\r\n') + '\n' + ENTRY

ts = time.strftime('%Y%m%d_%H%M%S')
shutil.copy2(A, f'{A}.bak_before_405_{ts}')
io.open(A, 'w', encoding='utf-8').write(t2)
print(f'  已追加 #405 · {len(t)} -> {len(t2)} 字符')
print(f'  备份: {os.path.basename(A)}.bak_before_405_{ts}')
