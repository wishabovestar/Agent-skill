# Agent-skill

本机 Hermes 智能体核心组件集（可复用脚本/工具）——随研究迭代同步更新。

## 组件清单

### 模型联邦与路由
- `model_federation.py` — 6 模型联邦引擎（planner/executor 角色分工）
- `model_specialize.py` — 模型专业化（任务→强项模型路由）
- `model_routing_engine` — 路由方法论（R27/dsh-routing-suite 落地）

### 自演化
- `gene_evolution.py` — 基因库演化（gene_pool 机制）
- `gene_weekly.py` — 基因周度轮（周二 9:00 评分+解锁推荐）
- `model_evo_accel.py` / `model_evo_batch.py` — 自演化加速/批处理
- `model_stability_guard.py` — 稳定性守护

### 蒸馏
- `distill_pipeline.py` — 蒸馏数据管道（大教师→小学生）
- `local_first_verify.py` — 本地优先验证

### 记忆
- `cortexmem_mode_search.py` — CortexMem 模式搜索（三层图+mem_judge）
- `think_ledger.py` — 思考账本（推理三铁律落地）

### 压缩与效率
- `tokenless_reducer.py` — Tokenless 压缩（R104 工具输出场景化）
- `unified_compressor.py` — 统一压缩器

### 索引与检索
- `hilbert_sort_index.py` — Hilbert 空间填充索引排序（R164 落地，AES 局部性 11-32x）

### 安全
- `credentials_vault.py` — 凭证保险库（AES-256-GCM+scrypt，R177/178 落地）
- `local_first_verify.py` — 本地优先验证（凭证守卫配合）

### 运营
- `vps_promo_autopilot.py` — VPS 推广自动巡航（周一 10:00 cron）
- `mixer_guard.py` — 8800 混合代理存活守护（/health 探测, R904 修复 404 误判）
- `local_first_mixer.py` — 已升 v2.4（R902: 三域路由+WHY/CAUSAL+SOFT_ASK 门+qwen2.5:7b 交叉复核）

### 形式化核验（数学五重验证+Lean 裸核心配套 — R903-R908）
- `frey2_base_check.py` / `frey2_adversarial.py` — Frey 全不变量系统五重基准+对抗审计（R903）
- `frey3_base_check.py` / `frey3_adversarial.py` — Frey 模 q 约化分类基准+前提必要性对照（R905）
- `pfr_ruzsa_check.py` — PFR Ruzsa 层（陪集平移/三角不等式/距离, 2400 万实例, R907）
- `pfr_cover_check.py` — PFR 覆盖结构穷举（F2³ 全 256 子集低倍增覆盖, R907）
- `lte_homology_check.py` — LTE 同调审计（SES 维数/Euler 语义/Hom 计数/Boolean 环, R908）

## 推送规范
- deploy key SSH（GIT_SSH_COMMAND 强制）
- 随研究迭代更新（R 系列归档→组件落地→推送）
