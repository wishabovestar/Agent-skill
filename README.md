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

### 多智能体协作（Swarm 式交接协议 — R1167）
- `agent_handoff.py` — Swarm 式**显式交接协议**：工具返回 Agent 即交接 + 零配置 DI（按形参名注入）+ 轨迹带 sender；15/15 自检 + 真实角色链实跑
  - ★ 三处**有意偏离上游**（不照抄）：`max_hops` 默认有限（上游 `inf`）／交接目标须存在于 registry（上游不校验）／检出交接环（上游无）

### 三层验证器与质量（R1143 / R1153 / R1164）
- `quality_verifier.py` — 层3 质量验证（引证**五档分级**、证据不足时**允许弃权**、台账落盘；14 项自检全绿）
- `assertion_trend.py` — 层2 断言趋势（AST 级断言计数回归，防"断言被悄悄删除"）
- `result_offload.py` — 工具结果卸载与翻页（★ `preview` 只读 n+1 字节：blob 2.99MB → 峰值内存 9,366B；19/19 自检 + 计数自证）

### 治理与审计（R1142 / R1164）
- `skill_spec_audit.py` — 技能规范**三桶审计**（本机扩展 vs 真未知；本地化判读后真违例 0）
- `skill_activation_audit.py` — 技能激活率审计（列名自适应 + 失败须响亮，不静默吞异常）
- `kb_index_coverage.py` — 知识库索引覆盖率断言（★ 已修正/反斜杠路径陷阱，曾致"域全 0"假报）

### 研究工具
- `paper_cand2.py` — 论文候选筛选（★ 修"字段名同义不同"坑：`labs_papers` 的内部 `id` 不是 arXiv id，须正则校验）

### 证据链逐环验证（待办落地 — R1169）
- `layer3_evidence_chain.py` — 层3 证据链**逐环**验证，补 R2 只查"有没有引用"的洞
  - C1 存在性 / C2 引文真实 / **C3 真支持(LLM)** / **C4 因果必要(LLM)** / C5 制度化
  - ★ **不假装 C3/C4 可机械判定** —— 只单列为待判项；C1/C2/C5 才是确定性的
  - 另含 **自洽检查**（reasoning 自陈放弃却给高分 ⇒ 判无效）与 **检测≠遏制**（detected/contained 分开 + gap）
  - 9/9 自检；★ C5 判别力实测：r1167(有落地件)=True，r1166/r1168(仅材料)=False

### Agent 集群治理
- `agent_tool_table_audit.py` — 角色工具表**校验**（幽灵工具 / ★「存在≠可用」/ 命名分裂 / 别名）
  - ★ 抓到真问题：`file`×2、`todo`（应 `todo_list`）、5 处 `web_extract`（存在但本机不可用）
  - 6/6 自检；★ 区分「名字对但暂时跑不了」与「名字根本不存在」，避免误删正确数据
- `fix_agent_tools.py` — 按审计结果修复 registry（备份 + 只动明确的点 + 顶层加字段语义说明）

## 推送规范
- deploy key SSH（GIT_SSH_COMMAND 强制）
- 随研究迭代更新（R 系列归档→组件落地→推送）
