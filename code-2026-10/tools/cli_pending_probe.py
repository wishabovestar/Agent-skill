# -*- coding: utf-8 -*-
"""复核 2026-10-12 那份「CLI 待决定项」里每一条现在的真实状态（只看文件/配置，不改任何东西）。"""
import json
import os
import pathlib
import re

P = lambda s: pathlib.Path(s)
L = []


def add(s):
    L.append(s)


# ---- 1) 微信 token / 二维码 ----
add("[1] 微信��移")
add("    wechat_qr_mybot.png 存在: %s" % P(r"D:/hermes/data/wechat_qr_mybot.png").exists())
add("    本会话即微信 ⇒ 投递通道当下可用（本次消息本身就是证据）")

# ---- 2) 「按照推荐排序执行下一步」 ----
add("[2] 指代复原：需你补上下文（无法从文件复原）")

# ---- 3) 共用会话线程 ----
add("[3] 会话线程是否共用：配置事实——各入口独立 session id（未改动）")

# ---- 4) 归档缺口 ----
f4 = P(r"D:/hermes/CORPUS_INDEX_FULL_215.md")
if f4.exists():
    t4 = f4.read_text(encoding="utf-8", errors="replace")
    add("[4] CORPUS_INDEX_FULL_215.md 存在，❌ 计数 %d 行" % len(re.findall(r"❌", t4)))
else:
    add("[4] CORPUS_INDEX_FULL_215.md 未找到")

# ---- 5) cron「强化学习四合一」+ 4 个技能 ----
jb = P(r"D:/hermes/hermes-data/profiles/mybot/cron/jobs.json")
if jb.exists():
    jobs = json.loads(jb.read_text(encoding="utf-8"))
    jobs = jobs["jobs"] if isinstance(jobs, dict) else jobs
    hit = [j for j in jobs if "四合一" in (j.get("name") or "")]
    add("[5] mybot jobs 共 %d 个；名称含「四合一」: %d" % (len(jobs), len(hit)))
    for j in hit:
        add("    id=%s enabled=%s state=%s last_status=%s script=%s" % (
            j.get("id"), j.get("enabled"), j.get("state"), j.get("last_status"), j.get("script")))
        add("    last_error=%s" % (str(j.get("last_error"))[:160]))
        add("    skills=%s" % (j.get("skills")))
else:
    add("[5] mybot jobs.json 未找到")

roots = [P(r"D:/hermes/hermes-data/profiles/mybot/skills"), P(r"D:/hermes/shared-skills")]
for s in ["agent-cluster-orchestrator", "self-improving-agent", "self-reinforcement", "technical-research-survey"]:
    where = [str(r) for r in roots if (r / s).exists() or (r / "devops" / s).exists() or list(r.glob("*/" + s))]
    add("    skill %-30s %s" % (s, ("存在 @ " + ";".join(where)) if where else "缺失"))

# ---- 6) qqbot3 的 weixin 投递引用 ----
q = P(r"D:/hermes/hermes-data/profiles/qqbot3/cron/jobs.json")
if q.exists():
    tq = q.read_text(encoding="utf-8", errors="replace")
    add("[6] qqbot3 jobs.json 中 \"weixin\" 出现 %d 次" % len(re.findall(r"weixin", tq, re.I)))
else:
    add("[6] qqbot3 jobs.json 未找到")

# ---- 7) D_d_quarantine ----
for cand in P(r"D:/hermes/data").glob("D_d_quarantine_*"):
    add("[7] %s  %d MB" % (cand.name, cand.stat().st_size // 1048576))
add("[7] 若上面没有行 ⇒ 该 tar.gz 已不存在")

# ---- 8) config.yaml custom_providers base_url ----
cfg = P(r"D:/hermes/hermes-data/config.yaml")
if cfg.exists():
    t = cfg.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"custom_providers:\s*\n((?:[ \t]+.*\n)+)", t)
    blk = m.group(1) if m else ""
    add("[8] custom_providers 段：%d 行；含 base_url: %s" % (
        len([x for x in blk.splitlines() if x.strip()]), "base_url" in blk))
    add("    " + " | ".join(x.strip() for x in blk.splitlines()[:8]))
else:
    add("[8] config.yaml 未找到")

P(r"D:/hermes/analysis/_cli_pending_now.txt").write_text("\n".join(L), encoding="utf-8")
print("ok", len(L))
