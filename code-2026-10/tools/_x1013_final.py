# -*- coding: utf-8 -*-
import json, os

DATE = "2026-10-13"
outdir = "D:/hermes/data/agent_knowledge/算法"
T = {t["repo"]: t for t in json.load(open(outdir + "/tmp/trending_parsed_1013.json", encoding="utf-8"))}
R = json.load(open(f"{outdir}/xuntian_github_scout_{DATE}.json", encoding="utf-8"))
V = {x.get("full"): x for x in json.load(open("D:/hermes/analysis/x1013_verified.json", encoding="utf-8")) if x.get("full")}
N = {x["full_name"]: x for x in R["new_all"]}
ALG = {x["full_name"]: x for x in json.load(open(f"{outdir}/algo_ext_{DATE}.json", encoding="utf-8"))["repos"]}

def info(name):
    t = T.get(name) or {}
    v = V.get(name) or {}
    n = N.get(name) or {}
    return {"stars": t.get("stars") or v.get("stars") or n.get("stars") or 0,
            "lang": (t.get("lang") or v.get("lang") or n.get("language") or "-"),
            "desc": (t.get("desc") or v.get("desc") or n.get("description") or ""),
            "gain": t.get("period_gain") or 0, "period": t.get("period") or "",
            "created": (v.get("created") or n.get("created_at") or "")[:10],
            "is_new": name in N}

# ---- curated Top 10 (Hermes / AI Agent toolchain) ----
TOP = [
    ("mattpocock/skills", 10, "+", "Trending 榜首：Real Engineers 的 Agent Skills 集合，直出 `.agents` 目录 — SKILL.md 编写范式的头部参考（Matt Pocock）"),
    ("affaan-m/ECC", 10, "+", "Agent harness 性能优化系统（Skills/Instincts/Memory/Security 四大件）— 与 Hermes harness 架构直接对标，月 +22.4k⭐"),
    ("anthropics/claude-code", 10, "+", "Anthropic 官方 agentic coding CLI — Agent 工具链标杆，持续高动量"),
    ("addyosmani/agent-skills", 10, "+", "Addy Osmani 出品的 production-grade AI 编码 Agent skills — 技能工程头部参考，周 +11.9k⭐"),
    ("vectorize-io/hindsight", 9, "+", "\"会学习的 Agent 记忆\"（Agent Memory That Learns）— 直接对应记忆优化方向，月 +25.2k⭐"),
    ("mksglu/context-mode", 9, "+", "AI 编码 Agent 的上下文窗口优化：工具输出沙盒化（98% 缩减）— 直接对应 Token/上下文压缩方向"),
    ("earthtojake/text-to-cad", 8, "+", "给 Agent CAD 超能力（text-to-CAD）— 构形/绘影 组的参数化 CAD 与图纸方向参考"),
    ("NVIDIA/OpenShell", 9, "+", "NVIDIA 出品的自主 AI Agent 安全私有运行时 — Agent 沙盒/安全边界参考，周 +7.3k⭐"),
    ("AgnesAI-Labs/agnes-harness", 10, "🆕", "可插拔 Agent Harness（Forward Deployed Engineer 场景）— harness 架构新增量，本轮首次入库"),
    ("lploc94/raw-cli", 10, "🆕", "\"The agent harness you can fork\"：含 compaction 的完整可用 agent loop — 轻量 harness 范本，本轮首次入库"),
]

# ---- remaining new high-value candidates (first-time archived) ----
NEW_SHOW = [
    "liyupi/ai-promo-video-maker", "loulanyue/agent-control", "iamumeransari/claude-show-your-work",
    "TencentCloud/octop-harness", "cv-cat/catbus", "cachix/agentaps",
    "marimuthu", "bdg9412/artex-ko-plus", "erictrainnlpinxihu/Grader-agent",
    "mmlong818/open-academic-paper-gen", "deeplethe/fde-gym", "Stonewuu/agenteam",
    "0xgetz/opencode-free-9router", "ftxcgwf/mcd-solver", "init-co-jp/diff-tour",
    "vdev-ctrl/Adaptive-Learnable-Hierarchical-Routing-", "data-goblin/claude-code-filetree",
    "HRuiCcc/RuiC-oc-ferry", "robertkarl/UnbiasedStrata",
]
NEW_SHOW = [n for n in NEW_SHOW if n in N]

lines = []
lines.append(f"# 巡天 GitHub 侦察报告 · {DATE}")
lines.append("")
lines.append(f"- **Trending**：daily 9 / weekly 11 / monthly 22（本地直连取回，合并去重 **{R['trending_count']}** 项）")
lines.append(f"- **Search**：{R['queries_total']} 组查询（主13+算法13+补充22+窄窗16）/ 候选池 {R['pool']} 条")
lines.append(f"- **知识库已见** {R['seen_repos']} 仓库 → 本轮唯一 {R['unique_repos']}，**新增 {R['new_count']}**（Agent {R['agent_new_count']} + 算法 {R['algo_new_count']}）")
lines.append("- 关键词：ai agent tool / mcp server / code assistant / search engine / cli tool + 算法/DL/NN 专项")
lines.append("")
lines.append("## 🏆 本周高价值 Top 10（Hermes / AI Agent 工具链相关）")
lines.append("")
lines.append("| # | 项目 | ⭐星数 | 语言 | 相关性 | 周期动量 | 推荐理由 |")
lines.append("|:--:|:--|--:|:--:|:--:|:--:|:--|")
for i, (nm, rr, badge, why) in enumerate(TOP, 1):
    d = info(nm)
    link = f"[{nm}](https://github.com/{nm})"
    gain = f"+{d['gain']:,}" if d["gain"] else "🆕新增"
    lines.append(f"| {i} | {link} | {d['stars']:,} | {d['lang']} | {rr}/10 | {gain} | {why} |")
lines.append("")
lines.append("> 说明：Top10 中前 8 位为本周 Trending 高动量项（已在库，作趋势锚点）；🆕 标记为本轮首次入库。")
lines.append("")
lines.append("## 🆕 本轮新增高价值候选（Search 新入库）")
lines.append("")
lines.append("| 项目 | ⭐ | 语言 | 相关性 | 创建 | 简介 |")
lines.append("|:--|--:|:--:|:--:|:--:|:--|")
for nm in sorted(NEW_SHOW, key=lambda k: -(N[k]["stars"] or 0)):
    x = N[nm]
    lines.append(f"| [{nm}]({x.get('url','')}) | {x['stars']:,} | {x.get('language') or '-'} | {x['relevance']}/10 | {(x.get('created_at') or '')[:10]} | {(x.get('description') or '')[:95]} |")
lines.append("")
lines.append("> 空壳剔除：`Superincrater/Autodesk-Revit`(sz=2)、`Cometamongrouse79/Crash-Plan`(sz=2) 及同批 `*48x` 关键词堆砌新仓（Discord/Total-Commander/KMS-Pico 等）经 `/repos/` 复核为空壳，已剔除。")
lines.append("")

algo_new = list(ALG.values())
lines.append("## 🧮 算法 / 深度学习 / 神经网络 新增采集")
lines.append("")
lines.append(f"共 **{len(algo_new)}** 条新增，已存入 `agent_knowledge/算法/`（`algo_ext_{DATE}.json` + `github_algo_scout_{DATE}.json`）：")
lines.append("")
for x in sorted(algo_new, key=lambda z: -(z["stars"] or 0))[:14]:
    lines.append(f"- **{x['full_name']}** ⭐{x['stars']:,} {(x.get('language') or '-')} ({(x.get('created_at') or '')[:10]}) — {(x.get('description') or '')[:110]}")
lines.append("")
lines.append("## 🔥 Trending 快照（Agent / 工具链 / 算法相关）")
lines.append("")
KEYS = ("agent", "mcp", "skill", "claude", "memory", "llm", "harness", "codex", "copilot", "cad",
        "context", "assistant", "local", "moe", "inference", "review", "plugin", "reverse", "sandbox")
snap = [x for x in R["trending"] if any(k in ((x.get("desc") or "") + x["repo"]).lower() for k in KEYS)]
for t in sorted(snap, key=lambda z: -(z.get("period_gain") or 0))[:18]:
    lines.append(f"- [{t['repo']}](https://github.com/{t['repo']}) ⭐{t['stars']:,} (+{t.get('period_gain',0):,} / {t.get('period','')}) — {(t.get('desc') or '')[:100]}")
lines.append("")

md = "\n".join(lines)
open(f"{outdir}/xuntian_github_scout_{DATE}.md", "w", encoding="utf-8").write(md)

R["top10"] = [{"rank": i, "full_name": nm, "stars": info(nm)["stars"], "lang": info(nm)["lang"],
               "relevance": rr, "reason": why, "url": f"https://github.com/{nm}",
               "period_gain": info(nm)["gain"], "is_new": nm in N}
              for i, (nm, rr, badge, why) in enumerate(TOP, 1)]
json.dump(R, open(f"{outdir}/xuntian_github_scout_{DATE}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("MD bytes:", len(md), "->", f"{outdir}/xuntian_github_scout_{DATE}.md")
print("new listed:", len(NEW_SHOW), "algo_new:", len(algo_new))
print("---- PREVIEW ----")
print(md[:2600])
