---
name: agent-shared-bridge
description: "Use when 与本地 DSH 互通、共享知识库/经验库/资料库。"
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [DSH, DeepSeek-Harness, interop, knowledge-base, bridge]
    related_skills: [hermes-kb, hermes-mcp-management]
---

# agent-shared-bridge — Hermes ⇄ DSH 互通

在 Hermes Agent 与本地 **DSH（DeepSeek Harness）** 之间共享知识库/经验库/资料库。

## When to Use / 何时用

* 需要把 Hermes 的**知识库/经验库/资料库**给 DSH 用（或反过来）
* 需要知道 **DSH 的接口面**（命令行、HTTP JSON-RPC、MCP 能力）
* 排查「两边数据不同步」

## 中立共享面

```
D:/agent-shared/
  bin/agent_bridge.py    唯一逻辑源（stdlib 优先；Hermes 3.14 与 DSH 3.12 都能跑）
  knowledge/  kb_entities.jsonl · kb_relations.jsonl · kb_INDEX.md
  memory/     <profile>__MEMORY.md · <profile>__USER.md   （已脱敏）
  library/    papers.jsonl · papers_INDEX.md
  from_dsh/   dsh_sessions.jsonl/.md · dsh_workspace_files.jsonl
  README.md
```

## 常用命令

```bash
B="D:/agent-shared/bin/agent_bridge.py"
python "$B" status       # 两边清单
python "$B" export       # Hermes 三库 -> 共享面（经验库自动脱敏）
python "$B" ingest-dsh   # DSH 会话/工作区 -> 共享面
python "$B" search all "关键词"   # scope: kb|memory|library|dsh|all
python "$B" verify       # 自检，exit 0 = 全过
```

DSH 侧用它的 shell 工具执行同一份 CLI（它自带 python 3.12 已实测可跑）。

## ⭐ MCP 层（推荐给 DSH）—— 别让模型敲命令行

共享面同时暴露为一个 **stdio MCP server**，DSH 挂上后直接拥有原生工具：
`mcp__hermes_shared__kb_search / memory_search / library_search / dsh_sessions / search_all / shared_status`

```
D:/agent-shared/bin/mcp_server.py      stdio MCP server（import agent_bridge，逻辑只有一份）
D:/agent-shared/dsh/APPEND_mcp-hermes-shared.yml      要追加到 cordis.patch.yml 的块
D:/agent-shared/dsh/cordis.patch.merged.yml           合并后的预览（不自动写入）
```

**关键事实（都是实测踩出来的）**
```
⚠️ DSH 自带 python【没有】 mcp 模块（3.12.14 实测）⇒ command 必须用
   C:\\Users\\Administrator\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\python.exe
⚠️ mcp 是【2.x】：FastMCP 已更名 MCPServer（mcp.server.mcpserver import MCPServer）；
   1.x 的路径是 mcp.server.fastmcp.FastMCP——本文件对两者都做了回退
⚠️ serverName 必须匹配 [A-Za-z0-9_-]{1,32} 且全局唯一；已存在的 serverName 是 `hermes`
   （那个 row 挂的是 `hermes mcp serve`，提供【消息/频道】10 工具）⇒ 本层用 `hermes_shared`
⚠️ 追加位置：进【已有】的 `- insert:` 列表末尾，不要新建第二个 `- insert:`
⚠️ DSH 改这个文件支持 HMR 热替换，不需要重启进程
```

**验证方式（配置驱动，不是手敲命令）**：读 merged.yml 里的 command/args/cwd 去起
`mcp.ClientSession` + `stdio_client`，做 initialize → tools/list → tools/call。
实测：server=hermes-shared、6 工具、7 次调用全部 ok、负向探针返回「无命中」。

## 铁律（不要绕过）

1. **经验库 fail-closed**：导出前必须过 `D:/hermes/analysis/security_sandbox.py:redact_secrets`。
   脱敏器不可用时 `export` **拒绝执行** —— 绝不降级成不脱敏照发。
2. **多用户隔离**：本机**多个 profile 分属不同用户**（业务与身份各不相同）。`export` 默认**只导当前 profile + 根共享**；
   要把别人的导出去必须显式 `--all-profiles`。跨用户泄漏是红线。
3. **源只读**：桥对 KB/memories/DSH home 只读，写入只发生在 `D:/agent-shared/` 内。
4. **别手改导出文件**：会被下次 `export` 覆盖（按内容哈希判重）。

## DSH 接口事实（已核实，勿再凭缓存文档猜）

⚠️ **教训**：判断 DSH 能力时**必须搜源码树** `D:/hermes/DeepSeek-Harness`，
不能只看缓存的 README —— 曾因此误判「DSH 不支持 MCP」。

| 事实 | 证据位置 |
|:--|:--|
| ✅ DSH 支持 MCP，**但只作客户端**（`mcp__<server>__<tool>`） | `packages/mcp/mcp-client/README.md` |
| ❌ DSH **不能**当 MCP server | 全库搜 `McpServer`/`StdioServerTransport` 无命中 |
| ✅ 本地 HTTP JSON-RPC `127.0.0.1:3080/api`，**无鉴权** | `packages/host/apiproxy/README.md` |
| ✅ 方法：`session.create/prompt/history/search`、`skill.list`、`subagent.*` | `packages/host/apiproxy/src/api/rpc-map.ts` |
| ✅ ACP / SDK stdio JSON-RPC（供外部编排） | `packages/acp/acp/`、`packages/sdk/server/` |
| ⚠️ `dsh` **不在 PATH**，`apps/cli/lib/bin.js` 无构建产物 | 需先 `pnpm install && pnpm run build` |
| 🚫 MCP 配置**不是** `.mcp.json` | 是 Cordis patch row，写进 `$DSH_HOME/cordis.patch.yml` 或 profile 的 `cordis.patch.yml` |

DSH 侧自己的侦察报告（信息量大，先读）：
`C:/Users/Administrator/Documents/deepseek-harness/default-workspace/recon/{dsh,hermes}-surface.md`

## 坑

* **no_agent cron 脚本必须用 `.py`**：`.sh` 交给 bash 跑，反斜杠会被吃掉 ⇒ exit 127。
* DSH 会话正文是 `session.v4.jsonl.zstd`（**多帧** zstd，需逐帧解）；明文索引
  `storages/session_projcache/sessions/*.json` 可直接读，字段常包成 `{ver,seq,val}`，取值要递归拆。
* `zstandard` 是本桥**可选**依赖：没有就只导元数据，不报错。
* 保活 cron：job `6fa1515eddde`（每日 07:00，静默，失败才推送）。
