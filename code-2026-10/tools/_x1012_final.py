# -*- coding: utf-8 -*-
import json, os

DATE = "2026-10-12"
outdir = "D:/hermes/data/agent_knowledge/算法"
T = {t["repo"]: t for t in json.load(open(outdir + "/tmp/trending_parsed_1012.json", encoding="utf-8"))}
R = json.load(open(f"{outdir}/xuntian_github_scout_{DATE}.json", encoding="utf-8"))
V = {x["full"]: x for x in json.load(open("D:/hermes/analysis/x1012_verified.json", encoding="utf-8")) if "full" in x}
N = {x["full_name"]: x for x in R["new_all"]}

def tinfo(name):
    t = T.get(name) or {}
    v = V.get(name) or {}
    n = N.get(name) or {}
    return {"stars": t.get("stars") or v.get("stars") or n.get("stars") or 0,
            "lang": (t.get("lang") or v.get("lang") or n.get("language") or "-"),
            "desc": (t.get("desc") or v.get("desc") or n.get("description") or ""),
            "gain": t.get("period_gain") or 0, "period": t.get("period") or "",
            "created": (v.get("created") or n.get("created_at") or "")[:10]}

TOP = [
    ("mattpocock/skills", 10, "Trending 榜首（286k⭐）：Real Engineers 的 Agent Skills 集合，直出 `.agents` 目录 — SKILL.md 编写范式的头部参考（Matt Pocock）"),
    ("affaan-m/ECC", 10, "Agent harness 性能优化系统（Skills/Instincts/Memory/Security 四大件）— 与 Hermes harness 架构直接对标，月 +22.5k⭐"),
    ("anthropics/claude-code", 10, "Anthropic 官方 agentic coding CLI — Agent 工具链标杆，持续高动量，月 +6.2k⭐"),
    ("NousResearch/hermes-official-plugins", 10, "☤ Nous Research 官方 Hermes Agent 插件集 — 与我方运行时同源，插件/hook 开发直接对标 🆕本轮新入库"),
    ("vectorize-io/hindsight", 9, "\"会学习的 Agent 记忆\"（Agent Memory That Learns）— 直接对应记忆优化方向，月 +24.9k⭐"),
    ("slopus/happy", 10, "一个 App 内编排 Claude / Codex / Grok 多 Agent（MIT）— 多 Agent 编排 + harness 互操作参考，日 +高动量"),
    ("Panniantong/Agent-Reach", 9, "给 Agent 一双眼睛：读取并搜索 Twitter/Reddit/全网（Python）— 巡天情报采集能力直接可借鉴"),
    ("danyuchn/asd-ste100-skill", 9, "ASD-STE100 简化技术英语规则做成 Claude Code Skill — 文档/写作类 skill 的优秀范式 🆕"),
    ("bherbruck/solidcraft", 8, "纯 Rust 开源参数化 3D CAD — 构形/绘影 组的 CAD 内核与参数化建模参考"),
    ("lawrencewzen/wx-bot", 9, "把微信接入你的 AI Agent（Grok/Muse/Claude）— 与 qqbot3 微信链路直接相关的桥接方案 🆕"),
]

new_hv = [x for x in R["new_all"] if x["relevance"] >= 6]
new_hv.sort(key=lambda x: -x["stars"])
skip = {"lawrencewzen/wx-bot", "danyuchn/asd-ste100-skill", "NousResearch/hermes-official-plugins", "slopus/happy"}
new_agent = [x for x in new_hv if x["full_name"] not in skip][:20]

lines = []
lines.append(f"# 巡天 GitHub 侦察报告 · {DATE}")
lines.append("")
lines.append(f"- **Trending**：daily 8 / weekly 12 / monthly 22（本地直连取回，合并去重 **{R['trending_count']}** 项）")
lines.append(f"- **Search**：{R['queries_total']} 组查询（主13+算法13+补充22）/ 候选池 {R['pool']} 条")
lines.append(f"- **知识库已见** {R['seen_repos']} 仓库 → 本轮唯一 {R['unique_repos']}，**新增 {R['new_count']}**（Agent {R['agent_new_count']} + 算法 {R['algo_new_count']}）")
lines.append("- 关键词：ai agent tool / mcp server / code assistant / search engine / cli tool + 算法/DL/NN 专项")
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
lines.append("> 说明：Top10 中部分为本周 Trending 高动量项（已在库，作趋势锚点）；🆕 标记为本轮首次入库。")
lines.append("")
lines.append("## 🆕 本轮新增高价值候选（Search 新入库）")
lines.append("")
lines.append("| 项目 | ⭐ | 语言 | 相关性 | 创建 | 简介 |")
lines.append("|:--|--:|:--:|:--:|:--:|:--|")
for x in new_agent:
    lines.append(f"| [{x['full_name']}]({x.get('url','')}) | {x['stars']:,} | {x.get('language') or '-'} | {x['relevance']}/10 | {(x.get('created_at') or '')[:10]} | {(x.get('description') or '')[:95]} |")
lines.append("")

algonames = [y["full_name"] for y in json.load(open(f"{outdir}/algo_ext_{DATE}.json", encoding="utf-8"))["repos"]]
algo_new = [x for x in R["new_all"] if x["full_name"] in algonames]
lines.append("## 🧮 算法 / 深度学习 / 神经网络 新增采集")
lines.append("")
lines.append(f"共 **{len(algo_new)}** 条新增，已存入 `agent_knowledge/算法/`（`algo_ext_{DATE}.json` + `github_algo_scout_{DATE}.json`）：")
lines.append("")
for x in sorted(algo_new, key=lambda z: -z["stars"])[:14]:
    lines.append(f"- **{x['full_name']}** ⭐{x['stars']:,} {(x.get('language') or '-')} ({(x.get('created_at') or '')[:10]}) — {(x.get('description') or '')[:110]}")
lines.append("")
lines.append("## 🔥 Trending 快照（Agent / 工具链相关）")
lines.append("")
KEYS = ("agent", "mcp", "skill", "claude", "memory", "llm", "harness", "codex", "copilot", "cad", "context", "assistant", "local")
snap = [x for x in R["trending"] if any(k in ((x.get("desc") or "") + x["repo"]).lower() for k in KEYS)]
for t in sorted(snap, key=lambda z: -(z.get("period_gain") or 0))[:16]:
    lines.append(f"- [{t['repo']}](https://github.com/{t['repo']}) ⭐{t['stars']:,} (+{t.get('period_gain',0):,} / {t.get('period','')}) — {(t.get('desc') or '')[:100]}")
lines.append("")

md = "\n".join(lines)
open(f"{outdir}/xuntian_github_scout_{DATE}.md", "w", encoding="utf-8").write(md)

R["top10"] = [{"full_name": nm, "stars": tinfo(nm)["stars"], "lang": tinfo(nm)["lang"],
               "relevance": rr, "reason": why, "url": f"https://github.com/{nm}",
               "period_gain": tinfo(nm)["gain"], "is_new": nm in N} for nm, rr, why in TOP]
json.dump(R, open(f"{outdir}/xuntian_github_scout_{DATE}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("MD bytes:", len(md), "->", f"{outdir}/xuntian_github_scout_{DATE}.md")
print("new_hv agent listed:", len(new_agent), "algo_new:", len(algo_new))
print("---- PREVIEW ----")
print(md[:3000])
