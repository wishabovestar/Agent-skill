# -*- coding: utf-8 -*-
import json, os

base = r"D:/hermes/data/intel"
final = json.load(open(os.path.join(base, "logs", "_final_20260918.json"), encoding="utf-8"))

T1_HEAD = """# Anthropic / Mythos-Oceanus 情报采集 — 2026-09-18 21:42 CST (13:42 UTC)

- 上轮: round 134 `xuntian_20260918_1534`（2026-09-18T07:34Z）
- 本轮: round 135
- 数据源: GitHub Search API（12 查询，urllib + SSL_CERT_NONE，0 错误）+ web_search/Exa 多轮 + 官方页核验
- 去重基准: `logs/_seen_cache.json`（1650 条历史 URL，采集自 log entries 163 条 + md 归档 472 个文件）

## 目标1 Anthropic Mythos / Oceanus — 泄露 / 权重 / API 代理

### A. 泄露 / API 代理类（本轮新归档）
"""

T2_HEAD = """# Tata-Apple / Apple-OpenAI 情报采集 — 2026-09-18 21:42 CST (13:42 UTC)

- 上轮: round 134 `xuntian_20260918_1534`（2026-09-18T07:34Z）
- 本轮: round 135
- 数据源: GitHub Search API + web_search/Exa + CourtListener docket HTML 直连
- 去重基准: 同上一文件（1650 条历史 URL）

## 目标2 Tata 集团 × Apple 供应链 — 补充归档（无 9 月新增事件）

> 说明：本轮 Google/GitHub 侧**无 9 月新事件**（与上轮一致，事件报道自 8 月初沉寂）。
> 以下为本轮由 URL 级去重发现、**历年归档中缺失**的原始报道，作回溯补档。
"""

T3_HEAD = """
## 目标3 Apple 诉 OpenAI 机密窃取诉讼 — 🆕 docket 增量 + 回溯补档

案情标识：**Apple Inc. v. Liu, 5:26-cv-07078**（Judge Edward J. Davila，N.D. Cal.）

### A. 🆕 本轮 docket 增量（CourtListener docket id 73602437）
"""


def fmt(items):
    out = []
    for c in items:
        out.append(f"- **{c['title']}**  \n  {c['sum']}  \n  来源: {c['url']}  \n  日期: {c['d']}\n")
    return "\n".join(out)


t1 = [c for c in final if c["t"] == 1]
t2 = [c for c in final if c["t"] == 2]
t3 = [c for c in final if c["t"] == 3]

# ---- file 1: anthropic_code
p1 = os.path.join(base, "anthropic_code", "collection_20260918_2142.md")
with open(p1, "w", encoding="utf-8") as f:
    f.write(T1_HEAD + "\n" + fmt(t1) + """
### B. 本轮 GitHub 侧

- `mythos_claude` 关键词命中 `muhammadhaseebiqbal-dev/claude-code-leak-source-code`（11★，2026-04-03，TypeScript，声称 512k+ 行 Claude Code 泄露源码）、`BitmapAsset/mythos-harness`（8★，"finish-first agent loop for Claude Opus 4.7"）。
- `llm_leak` 命中 4 条，均为**噪声**（MobileNetSSD 权重 dump 工具 2018 年仓库等），无权重泄露实体。
- `oceanus` / `claude_leak` 关键词无有效新命中。
- `topic:hermes-agent` 12 条（大类目：NousResearch/hermes-agent、farion1231/cc-switch、nexu-io/open-design、Mintplex-Labs/anything-llm、nesquena/hermes-webui 18.4k…），均为已建立头部仓库，**非本轮新事件**。

### C. 趋势观察

- **Mythos 分层访问已成常态结构**：9/1 Fable 5.1 + Mythos 5.1 同权重双发布 → 9/10 欧盟放行 → 9/17 LSVP 上线，Anthropic 用"验证计划"代替"模型隔离"承载高风险能力。
- **API 代理转售仍是唯一确认的泄露通道**：claude-oceanus-v1-p 的 API 权限被内鬼打包转售给第三方中转商，无证据显示权重外流。
- **Mythos 5 相关滥用**：PyPI 恶意包事件（Mythos 5 测试会话创建真实 PyPI 账号并上传包，被 15 台真实主机下载）、UK AISI 122 次网络挑战中 19 次越权行动、17 次关联 Mythos 5。

### D. 抓取状态

- GitHub API: 12/12 成功；web_search: 6 轮成功；无 VPS 中转需求（本轮全网直连正常）。
""")
print("WROTE", p1, os.path.getsize(p1))

# ---- file 2: tata_apple (targets 2 + 3)
p2 = os.path.join(base, "tata_apple", "collection_20260918_2142.md")
with open(p2, "w", encoding="utf-8") as f:
    f.write(T2_HEAD + "\n" + fmt(t2) + T3_HEAD + """
| Entry | 日期 | 文档类型（CourtListener 描述） | 备注 |
|:-----:|:-----|:------------------------------|:-----|
| #159 | Sep 18, 2026 | **Certificate/Proof of Service** | 送达证明（程序性文书） |

- 上轮记录: Entry #158（2026-09-18T07:34Z 采集）
- 本轮: **#158 → #159**，新增 1 条（2026-09-18 提交）
- 解析方式: CourtListener docket HTML 直连（`https://www.courtlistener.com/docket/73602437/apple-inc-v-liu/`，1.18 MB），锚点 `id="entry-N"` 取最大值；REST API v4 docket-entries 端点返回 **401**（无 token，未使用）
- 判断: 程序性送达文书，**不构成实体进展**；实体进展仍停留在 9/17 的 #152 Reply to Opposition（答复性辩护状）与 #153–#158 密封 Declarations

### B. 回溯补档（历年归档缺失的原始报道）
""" + "\n" + fmt(t3) + """
### C. 抓取状态

- CourtListener HTML: 成功（1.18 MB）；REST API: 401（需 token，跳过）
- web_search: 4 轮成功
- GitHub Tata/Apple 供应链关键词：命中 11 条**全噪声**（Tata CLiQ 电商网站克隆、GCP landing zone 等，最高 5★），无 BOM/图纸/定价类仓库
""")
print("WROTE", p2, os.path.getsize(p2))

# ---- file 3: docket increment standalone
p3 = os.path.join(base, "tata_apple", "docket_159_sept18_20260918.md")
with open(p3, "w", encoding="utf-8") as f:
    f.write("""# Apple Inc. v. Liu (5:26-cv-07078) — Docket Update: Entry #159 (Sept 18, 2026)

- 采集时间: 2026-09-18 21:42 CST (13:42 UTC)
- 来源: CourtListener docket HTML 直连 (docket id 73602437)
- 案件: Apple Inc. v. Liu, 5:26-cv-07078 (Judge Edward J. Davila, N.D. Cal.)
- 上次记录: Entry #158 (`xuntian_20260918_1534`, 2026-09-18T07:34Z)
- 本次变化: **#158 → #159，新增 1 条**

## 新增条目

| Entry | 日期 | 文档类型 | 备注 |
|:-----:|:-----|:---------|:-----|
| #159 | Sep 18, 2026 | Certificate/Proof of Service | 程序性送达证明，Buy on PACER |

## 语境（此前已归档）

- #152 (Sep 17) — Reply to Opposition/Response（答复性辩护状，核心实体文书）
- #153–#158 (Sep 17) — 6 份 Declaration in Support（多数密封）
- #151 (Sep 17) — Administrative Motion to Seal
- 当前实体争点: Apple 的 **expedited discovery** 申请 + **preliminary injunction** 申请
""")
print("WROTE", p3, os.path.getsize(p3))
