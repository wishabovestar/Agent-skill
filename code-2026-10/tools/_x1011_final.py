# -*- coding: utf-8 -*-
import json, os, datetime

DATE = "2026-10-11"
outdir = "D:/hermes/data/agent_knowledge/算法"
T = {t["repo"]: t for t in json.load(open(outdir + "/tmp/trending_parsed_1011.json", encoding="utf-8"))}
R = json.load(open(f"{outdir}/xuntian_github_scout_{DATE}.json", encoding="utf-8"))
V = {x["full"]: x for x in json.load(open("D:/hermes/analysis/x1011_verified.json", encoding="utf-8"))}
N = {x["full_name"]: x for x in R["new_all"]}

def tinfo(name):
    t = T.get(name) or {}
    v = V.get(name) or {}
    n = N.get(name) or {}
    return {"stars": t.get("stars") or v.get("stars") or n.get("stars") or 0,
            "lang": (t.get("lang") or v.get("lang") or n.get("language") or "-"),
            "desc": (t.get("desc") or v.get("desc") or n.get("description") or ""),
            "gain": t.get("period_gain") or 0, "period": t.get("period") or ""}

# curated Top 10 high-value (week's hottest agent/toolchain + fresh finds)
TOP = [
    ("affaan-m/ECC", 10, "Agent harness 性能优化系统（Skills/Instincts/Memory/Security 四大件）— 与 Hermes harness 架构直接对标，本月 +22.7k⭐"),
    ("anthropics/claude-code", 10, "Anthropic 官方 agentic coding CLI — Agent 工具链标杆，持续高动量"),
    ("vectorize-io/hindsight", 9, "\"会学习的 Agent 记忆\"（Agent Memory That Learns）— 直接对应记忆优化方向，月 +24.6k⭐"),
    ("multica-ai/andrej-karpathy-skills", 9, "Karpathy 行为准则凝练的 CLAUDE.md — 名人追踪信号，218k⭐"),
    ("addyosmani/agent-skills", 8, "生产级 AI 编码 Agent 技能集 — SKILL.md 编写范式参考，月 +11.2k⭐"),
    ("thedotmack/claude-mem", 9, "跨会话持久上下文/记忆层（Every Agent）— 记忆扩展直接可借鉴"),
    ("alibaba/open-code-review", 7, "阿里规模验证的安全高效 AI 代码审查 — 守序/铸盾组参考，月 +23k⭐"),
    ("mksglu/context-mode", 10, "编码 Agent 上下文窗口优化 + 沙盒 — Token 优化/上下文工程直接相关"),
    ("morluto/rea", 5, "Agent 驱动逆向工程（app→native binaries）— 破阵/铸盾安全组参考，日 +25.8k⭐"),
    ("antfu/skills-pack", 10, "Anthony Fu 精选 agent skills 包 — 本轮新入库，社区头部开发者新动作 🆕"),
]

# new (this-run) high-value
new_hv = [x for x in R["new_all"] if x["relevance"] >= 6]
new_hv.sort(key=lambda x: -x["stars"])
new_agent = [x for x in new_hv if x["full_name"] not in ("antfu/skills-pack",)][:18]

lines = []
lines.append(f"# 巡天 GitHub 侦察报告 · {DATE}")
lines.append("")
lines.append(f"- **Trending**：daily 13 / weekly 13 / monthly 23（VPS 中继取回，合并去重 **{R['trending_count']}** 项）")
lines.append(f"- **Search**：{R['queries_total']} 组查询 / 候选池 {R['pool']} 条（主13+算法13+补充22）")
lines.append(f"- **知识库已见** {R['seen_repos']} 仓库 → 本轮唯一 {R['unique_repos']}，**新增 {R['new_count']}**（Agent {R['agent_new_count']} + 算法 {R['algo_new_count']}）")
lines.append(f"- 关键词：ai agent tool / mcp server / code assistant / search engine / cli tool + 算法/DL/NN 专项")
lines.append("")
lines.append("## 🏆 本周高价值 Top 10（Hermes / AI Agent 工具链相关）")
lines.append("")
lines.append("| # | 项目 | ⭐星数 | 语言 | 相关性 | 周期动量 | 推荐理由 |")
lines.append("|:--:|:--|--:|:--:|:--:|:--:|:--|")
for i, (nm, rr, why) in enumerate(TOP, 1):
    info = tinfo(nm)
    link = f"[{nm}](https://github.com/{nm})"
    gain = f"+{info['gain']:,}" if info["gain"] else "🆕新增"
    lines.append(f"| {i} | {link} | {info['stars']:,} | {info['lang']} | {rr}/10 | {gain} | {why} |")
lines.append("")
lines.append("> 说明：Top10 项目多为本周 Trending 高动量项（已在库，作趋势锚点）；🆕 标记为本轮首次入库。")
lines.append("")
lines.append("## 🆕 本轮新增高价值候选（Search 新入库）")
lines.append("")
lines.append("| 项目 | ⭐ | 语言 | 相关性 | 创建 | 简介 |")
lines.append("|:--|--:|:--:|:--:|:--:|:--|")
for x in new_agent:
    lines.append(f"| [{x['full_name']}]({x.get('url','')}) | {x['stars']:,} | {x.get('language') or '-'} | {x['relevance']}/10 | {(x.get('created_at') or '')[:10]} | {(x.get('description') or '')[:90]} |")
lines.append("")
algo_new = [x for x in R["new_all"] if x["full_name"] in [y["full_name"] for y in json.load(open(f"{outdir}/algo_ext_{DATE}.json", encoding="utf-8"))["repos"]]]
lines.append("## 🧮 算法 / 深度学习 / 神经网络 新增采集")
lines.append("")
lines.append(f"共 **{len(algo_new)}** 条新增，已存入 `agent_knowledge/算法/`（`algo_ext_{DATE}.json` + `github_algo_scout_{DATE}.json`）：")
lines.append("")
for x in sorted(algo_new, key=lambda z: -z["stars"])[:12]:
    lines.append(f"- **{x['full_name']}** ⭐{x['stars']:,} {(x.get('language') or '-')} ({(x.get('created_at') or '')[:10]}) — {(x.get('description') or '')[:110]}")
lines.append("")
lines.append("## 🔥 Trending 快照（Agent/工具链相关）")
lines.append("")
for t in sorted([x for x in R["trending"] if any(k in ((x.get("desc") or "") + x["repo"]).lower() for k in ("agent","mcp","skill","claude","memory","llm","harness","codex","copilot"))], key=lambda z: -(z.get("period_gain") or 0))[:14]:
    lines.append(f"- [{t['repo']}](https://github.com/{t['repo']}) ⭐{t['stars']:,} (+{t.get('period_gain',0):,} / {t.get('period','')}) — {(t.get('desc') or '')[:100]}")
lines.append("")

md = "\n".join(lines)
open(f"{outdir}/xuntian_github_scout_{DATE}.md", "w", encoding="utf-8").write(md)

# update JSON top10 with curated
R["top10"] = [{"full_name": nm, "stars": tinfo(nm)["stars"], "lang": tinfo(nm)["lang"],
               "relevance": rr, "reason": why, "url": f"https://github.com/{nm}",
               "period_gain": tinfo(nm)["gain"], "is_new": nm in N} for nm, rr, why in TOP]
json.dump(R, open(f"{outdir}/xuntian_github_scout_{DATE}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("MD bytes:", len(md), "->", f"{outdir}/xuntian_github_scout_{DATE}.md")
print("new_hv agent:", len(new_agent), "algo_new:", len(algo_new))
print("---- PREVIEW ----")
print(md[:2600])
