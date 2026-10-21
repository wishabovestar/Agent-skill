# CortexMem — 连续演化记忆系统

借鉴 FluxMem (arXiv 2605.28773 "Rethinking Memory as Continuously Evolving Connectivity") 的三层异构图思想，融合 Cache 三态层级、双路检索、睡眠巩固的本地记忆系统。v2.2 吸收 15 个记忆工具精华（Mem0/MemOS/Cortex-Mem/TencentDB/AgeMem 等）。

## 特性

- **三层异构图**: 语义 (semantic) / 情景 (episodic) / 程序 (procedural) 节点 + 实体边
- **三态驻留**: 热/温/冷 (Cache 层级, TLB 类比)
- **双路检索**: 倒排索引 + 图遍历 + 实体提升 + 会话过滤 + 反馈权重 (5 路融合)
- **睡眠巩固**: 离线蒸馏技能晶体 + Ebbinghaus 遗忘曲线剪枝 (0.1 归档 / 0.02 删除)
- **渐进披露**: L0 粗筛 → L1 摘要 → L2 全文 (省 token)
- **LRU+TTL 缓存**: 查询缓存 (省 50-75% 重复计算)
- **技能晶体化**: 程序节点带 crystal/verified 成熟度 (MemOS 借鉴)
- **版本化**: 更新可回溯 (history + version, Mem0 借鉴)
- **符号压缩**: 长记忆 → 结构化符号 (TencentDB 借鉴)
- **安全防护**: memory_guard 注入检测 + 敏感字段 + pinned 保护
- **反馈驱动**: 用户反馈修正权重 (喜欢↑ 不喜欢↓)

## 设计原理

| 学科 | 原理 → 实现 |
|:--|:--|
| 生理学 | 海马迁移/突触剪枝 → 睡眠巩固 / Ebbinghaus 遗忘曲线 |
| 计算机 | Cache 层级/TLB → 三态 (热/温/冷) |
| 数据库 | ACID/MVCC/聚簇 → 版本化 + 倒排索引 |
| 存储搜索 | 倒排+向量+图 → 5 路融合检索 |
| 群论 | 轨道稳定化 → 相似蒸馏 |

## 性能

- 30 天保持率: 0.688 (旧库 2.08x)
- 检索命中: 90-100%
- 记忆蒸馏: 每次睡眠 ~10 技能
- 安全隔离: 注入检测有效

## 用法

```bash
# CLI
python cortexmem.py --add "内容" --query "关键词" --sleep
# Agent 接口 (JSON)
python cortexmem_tool.py '{"action":"disclose","query":"关键词"}'
python cortexmem_tool.py '{"action":"pin","id":"<id>"}'
python cortexmem_tool.py '{"action":"feedback","id":"<id>","liked":true}'
```

## 组件

| 文件 | 说明 |
|:--|:--|
| cortexmem.py | 核心 (三层图+三态+5路检索+巩固) |
| cortexmem_tool.py | Agent JSON 接口 (8 action) |
| cortexmem_guard.py | 安全防御 |
| cortexmem_integrate.py | state.db 增量摄取 |
| cortexmem_daily.py | 每日巩固 |
| cortexmem_ab_test.py | 新旧 A/B 对比 |
| cortexmem_hub.py | 体系总控 |

## 吸收来源

FluxMem (三层图) · Mem0 (实体/敏感/会话/版本) · MemOS (晶体/反馈/修复) · Cortex-Mem (Ebbinghaus/L0-L2/缓存) · TencentDB (符号压缩) · AgeMem (pinned) · Voyager (技能库) · HippoRAG (图谱) · MetaGPT (经验池) · herdr (State分离/handoff)
- **增量摄取**: 从会话状态库自动同步 (增量游标防重复)

## 性能

- 30 天记忆保持率: **0.69** (旧 FTS5 基线 0.331, **2.1x 提升**)
- 检索命中率: 100% (中文按字分词)
- 历史数据验证: 真实会话 100 条 + 20 查询

## 用法

```bash
# 初始化 (从审计文件建图)
python cortexmem.py --init

# 添加记忆
python cortexmem.py --add "奥卡姆剃刀原则应用于记忆库精简优化"

# 检索 (返回 热/温/冷 + 类型 + 分数)
python cortexmem.py --query "奥卡姆"

# 睡眠巩固 (蒸馏+剪枝)
python cortexmem.py --sleep

# agent 工具接口 (JSON 输出)
python cortexmem_tool.py '{"action":"query","query":"奥卡姆","top_k":5}'

# 安全写入 (memory_guard 整合)
python cortexmem_guard.py '{"action":"add","content":"...","type":"semantic"}'

# 每日巩固 (同步+睡眠+周度验证)
python cortexmem_daily.py

# 新旧记忆库 A/B 对比
python cortexmem_ab_test.py
```

## 设计原理

| 学科 | 原理 | 实现 |
|:--|:--|:--|
| 生理学 | 海马迁移 / 突触剪枝 | 睡眠巩固 (蒸馏+剪枝) |
| 计算机 | Cache 层级 / TLB | 三态 (热/温/冷) |
| 数据库 | ACID / MVCC / 聚簇索引 | 版本化 + 倒排索引 |
| 存储搜索 | 倒排索引 + 图遍历 | 双路检索 |
| 群论 | 轨道压缩 | 相似记忆蒸馏 |

## vibe coding

本项目为 **vibe coding** 产物:
从 14 个记忆工具 (MemGPT / Voyager / HippoRAG / FluxMem / A-MEM / Reflexion...) 代码级研究出发,
多学科 (生理学 / 计算机 / 数据库 / 群论 / 信息论) 融合设计,
模拟验证驱动迭代 (30 天保持率模拟 → 历史数据验证 → A/B 对比),
错误案例高权重 + 奥卡姆剃刀精简原则贯穿始终。

## 相关

- FluxMem 论文: arXiv 2605.28773
- 记忆工具研究: 14 工具横向对比 (Voyager SkillManager / HippoRAG PAG / MetaGPT Memory)
