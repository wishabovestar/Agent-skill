---
name: dsh-bridge
description: "Delegate heavy coding/agent work to the local DeepSeek Harness (dsh) runtime, and reach Hermes messaging from dsh. Use when a task needs dsh's own agent loop, sandbox, or a long autonomous run."
version: 1.0.0
author: local-integration
license: MIT
metadata:
  hermes:
    tags: [dsh, deepseek-harness, delegation, bridge, coding-agent]
    related_skills: [claude-handoff, handoff]
---

# dsh-bridge

Two-way local bridge between Hermes and **dsh** (DeepSeek Harness, the DeepSeek AI
agent harness installed on this machine). No network hop: both directions are local
process/stdio links.

## Hermes -> dsh

Plugin `dsh-bridge` (enabled) registers two tools:

| Tool | Purpose |
|---|---|
| `dsh_task` | Run one task in a dsh agent session and return its final answer. |
| `dsh_status` | Show resolved launcher, version, profile, workspace, patch state. |

`dsh_task` arguments: `task` (required), `workspace`, `profile` (default `headless`),
`timeout_seconds` (default 900, max 3600), `patch`. It runs
`dsh --profile <profile> "<task>"`, which boots a **fresh persisted dsh session**,
runs to quiescence, prints the last assistant message, and exits (0 on success).

When to use it:

- The work needs its own autonomous agent loop over a repository (multi-step edits,
  test-fix cycles) rather than one-shot tool calls.
- You want a second, independent model session on the same codebase.
- You want to hand off a long run instead of holding this conversation open.

When **not** to use it:

- It is one-shot only: no follow-up turn, no streaming, no shared context with the
  dsh desktop app. Put the whole task in `task`.
- It is a fresh session every call, so pass a `workspace` if the task depends on a
  repo, and expect no memory of previous `dsh_task` calls.
- It costs a full second agent run; keep prompts self-contained.

Example: `dsh_task(task="In <repo> fix the failing tests and report the root cause.",
workspace="D:\\work\\myrepo", timeout_seconds=1800)`.

## dsh -> Hermes

Config only, no code: `$DSH_HOME/cordis.patch.yml` mounts
`@deepseek-ai/dsh-mcp-client` over `hermes mcp serve` (stdio). Every dsh profile —
including the DeepSeek Harness desktop app — sees these tools as `mcp__hermes__*`:

`channels_list`, `conversations_list`, `conversation_get`, `messages_read`,
`messages_send`, `events_poll`, `events_wait`, `attachments_fetch`,
`permissions_list_open`, `permissions_respond`.

So a dsh agent can send to / read Feishu, DingTalk, WeChat and the other connected
platforms directly: `mcp__hermes__messages_send(target="feishu:oc_...", message="...")`.

## ⭐ 能力矩阵：按【能力】分配，不按任务形状猜

`python D:/hermes/analysis/agent_router.py caps` 打印判据表。**只有实测过的才写 yes/no；没测的一律 unknown**
（unknown 在决策层等同“不具备” ⇒ 保守留在 Hermes）。每条带 `evidence`（凭什么这么说）与 `reopen_if`（什么条件下翻转）。

| 能力 | HERMES | DSH | 依据 |
|:--|:--:|:--:|:--|
| shell.exec | yes | **BLOCKED** | 实测 DSH 报 `sandbox escalation to "danger-full-access" requires approval, but no approval channel is available` |
| fs.read / fs.write | yes | yes | 实测 DSH 在指定 cwd 落盘并读回 3 B 文件 |
| agent.loop | yes | yes | 实测 DSH 输出 reasoning 轨迹（规划→调用→自验证→回报） |
| agent.longhorizon | bounded | yes | `headless` = 答一个任务到静默为止；Hermes 会话受 max_turns 约束 |
| mcp.consume | yes | yes | 源码级：DSH 有 mcp-client 插件；本机已挂 mcp-hermes |
| skills.load | yes | no | 技能是 Hermes 概念（SKILL.md / external_dirs）；DSH 用 Cordis 插件树 |
| messaging.send / cron.schedule / kb.read / net.fetch | yes | **unknown** | 未实测 ⇒ 一律不派给 DSH |

**规则顺序（前者否决后者）**
```
G0  dsh 不可用        → HERMES（绝不路由到死端）
G0b headless profile 缺失 → HERMES
R1  命中 Hermes 独有      → HERMES（一票）
⭐C1 任务所需能力 dsh=no/blocked/unknown → HERMES（一票）★ 这是“按能力分配”的核心
R2  今日配额用尽      → HERMES（降级，不排队）
R3  并发锁被占        → HERMES
R4  自主分 >=6        → DSH
R5  自主分 4..5       → HERMES（模糊带，提示“把长程意图写进任务”）
R6  默认              → HERMES（宁直答勿滥调度）
```

⭐ **C1 的直接后果（实测用例）**：「clone 仓库跑测试一直修到全绿」这类任务在能力矩阵落地前会被派给 DSH，
现在**正确的行为是留在 Hermes** —— 因为它需要 shell，而 DSH 沙箱不给。
⇒ 能力闸优先于“显式指名 dsh”：**任务里写了“用 dsh”也拦得住**。

⚠️ 写测试时的坑：含 shell 的任务会**先被 C1 拦下**，所以验证 R2（预算闸）必须用【不触发 C1】的任务；
否则看到的是 C1 而不是 R2，会误判为“预算闸坏了”。

## 动态路由（谁该干这条活）

`D:/hermes/analysis/agent_router.py` —— 把「该 Hermes 还是该 dsh」从人判断变成**可观测、可审计、可复现**的决策，并**真的调起**对应一侧。

```bash
R="D:/hermes/analysis/agent_router.py"
python "$R" signals                     # 探测信号（带 300s 缓存）
python "$R" decide "<任务>" [--json]      # 只决策，落日志
python "$R" run "<任务>" [--dry-run]     # 决策 + 执行
python "$R" log --tail 20               # 审计决策日志
python "$R" selftest                    # 4 正向 + 2 能力闸（正/负向）+ 2 负向 = 8 例
```

**两条执行路径（都是真调起）**
```
DSH    dsh.cmd --profile headless "<task>"        一次性自主运行，打印最后一条助手消息
HERMES hermes.exe -p <当前profile> -z "<task>"     一次性文本应答（profile 用 HERMES_ROUTE_PROFILE 指定）
```

**观测量 / 阈值 / 阈值附近怎么办**（纪律：每条规则三项齐全）

| 规则 | 观测量 | 阈值 | 阈值附近 |
|:--|:--|:--|:--|
| G0 硬闸 | `dsh_available`（dsh.cmd 存在且 `--version` rc=0） | 布尔 | 不可用**绝不**路由过去 |
| G0b 硬闸 | `headless` profile 存在 | 布尔 | 缺则无法一次性运行 |
| R1 一票 | 是否命中 Hermes 独有（消息/定时/记忆知识库/技能/浏览器/PPT/本会话） | ≥1 命中即留本地 | 一票否决，不走打分 |
| ⭐ **C1 一票** | **任务所需能力在 `CAPS` 里的 dsh 值**（见上节能力矩阵） | `no` / `blocked` / `unknown` 任一命中即留本地 | 一票否决；**优先级在 R2 之前** |
| R2 预算 | `dsh_calls_today` vs `ROUTE_DSH_DAILY_CAP`（默认 20） | `>=` 即降级 | 超限降级到本地，不排队 |
| R3 并发 | `dsh_run.lock` 是否存在 | 布尔 | 撞车则留本地，避免并发 |
| R4 主判定 | `autonomy_score`（仓库+2 / 测试构建+3 / 多步实现+2 / 长程自主+2 / 沙箱+1 / 大范围+1 / 显式指名+5） | `>=6` ⇒ DSH | — |
| R5 模糊带 | 同上 | `4..5` ⇒ **保守留本地**并提示“把长程意图写进任务” | 明确告知怎么越过阈值 |
| R6 默认 | 同上 | `<4` ⇒ 留本地（宁直答勿滥调度） | — |

每条决策落 `D:/agent-shared/state/route_decisions.jsonl`，字段含 `rule / reason / signals 快照 / threshold_distance / outcome / duration_s`。
每条规则带 `reopen_if`（例：R4 的翻转条件是「实测 dsh 侧失败率高于本地」——看日志的 outcome）。

**⭐ 本机路径坑（实测踩到）**
```
⚠️ dsh.cmd 【不在】%USERPROFILE% 下 —— 桌面版装到了 D:\Users\Administrator\...
   （装到 D 盘但保留了 Users 路径结构）⇒ 只信 HOME 会报 launcher-not-found。
   正解：多候选扫描（DSH_CLI 环境变量 → D:/Users/... → C:/Users/... → 两盘 glob）
⚠️ `dsh --profile desktop --dump-config` 会被拒：
   error: profile "desktop" is managed exclusively by the Electron application
   ⇒ 要验证 compose 树用 `--profile headless --dump-config`（exit 0，约 12 KB）
```

**⭐⭐ 两条实测的硬约束（不记就会踩，已改代码而非只记坑）**

```
① cwd 不能靠猜：`dsh headless --help` 只有 --json / --session-id，【没有 workspace/cwd 选项】。
   它写的文件落在【继承来的进程 cwd】里。
   ⇒ 调用方必须显式传 cwd（subprocess 的 cwd=），否则产物落到当前 shell 所在的任意目录。
   agent_router.py 已加 --cwd / AGENT_ROUTER_DSH_CWD，默认 D:/agent-shared/workspace。
   实测：不传 ⇒ 文件落到 cache/scratch（当时 shell 的 cwd）；传 --cwd ⇒ 落到指定目录 ✓

② ⚠️ headless 跑在【沙箱】里，shell 命令需要审批，而无人值守时没有审批通道：
      Error: sandbox escalation to "danger-full-access" requires approval,
             but no approval channel is available
   ⇒ 【文件工具可用，shell 命令会失败】。
   ⇒ 后果：R4 把「clone 仓库 / 跑测试 / 修到全绿」这类任务路由给 DSH 的前提被打脸 ——
      那类任务恰恰离不开 shell。当前只有【纯文件操作 / 分析 / 生成】类任务可安全路由。
   ⚠️ 在上游提供无人值守审批或白名单前，别把依赖 shell 的任务当可靠路由对象。
```

**验证方式（决定性探针）**：让 DSH 自报 cwd 并落一个带唯一名的文件，再去两个候选目录查它落在哪 ——
只看 stdout 里的自我描述不够（它可能读的与写的不是同一个地方）。

## Health checks

```
hermes plugins show dsh-bridge                      # enabled?
hermes plugins validate HERMES_HOME/plugins/dsh-bridge
hermes -z "call dsh_status and print the JSON" --yolo --cli
"D:\...\resources\runtime\cli\bin\dsh.cmd" --profile headless --dump-config   # expect an mcp-hermes row
```

## Disconnecting

- Hermes -> dsh: `hermes plugins disable dsh-bridge`.
- dsh -> Hermes: replace `$DSH_HOME/cordis.patch.yml` with `[]` (or delete it).