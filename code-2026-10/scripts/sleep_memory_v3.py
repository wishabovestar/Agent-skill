#!/usr/bin/env python3
"""
改进版睡眠记忆引擎 v3 — 基于真实睡眠神经生理
=============================================
生理机制 → 算法映射:
  [SWS慢波-尖波耦合] 分层处理强度
  突触稳态假说      → 连续强度演化(替代硬阈值剪枝)
  海马时序重放      → 按时间顺序重放+时空压缩(摘要)
  NREM-REM多循环    → 4-6轮迭代巩固(弱→衰减, 强→强化)
  情绪记忆(杏仁核)  → 情绪词加权强化
  REM跨域整合      → 跨域抽象泛化
  TMR定向重激活    → 目标记忆线索定向增强
"""
import json, sqlite3, os, sys, re, math, random
from collections import defaultdict
from datetime import datetime, timedelta

DB_PATH = "D:/hermes/hermes-data/profiles/qqbot3/state.db"
KB_DIR = "D:/hermes/hermes-data/profiles/qqbot3/knowledge_base"
OUTPUT_DIR = f"{KB_DIR}/audit"

# ── 生理参数 (对应神经机制) ──
SYNAPTIC_DECAY = 0.85       # 突触渐进衰减因子(每次循环)
PLASTICITY_GAIN = 0.20      # 重要性→强度增强增益(长时程增强)
EMOTION_WEIGHT = 1.5        # 情绪记忆加权(杏仁核强化)
NUM_CYCLES = 4              # NREM-REM循环数(生理4-6)
REPLAY_COMPRESS = 0.2       # 时空压缩(摘要比例)
MID_BAND_RETAIN = 0.5       # 中等强度记忆保留因子 — AB-SLEEP-02对齐: promote 18→20%边际为正(F1 +1.05pp),
                            # 映射为"提高中等强度记忆保留率"(0.3→0.5, 原硬编码0.3; 低风险, 可回退)

# ── 情绪词库 (杏仁核强化) ──
EMOTION_WORDS = ["重要", "关键", "严重", "危机", "紧急", "危险", "热爱", "兴奋",
                 "兴趣", "关注", "偏好", "喜欢", "愤怒", "害怕", "担心", "成功",
                 "失败", "重要!", "critical", "urgent", "important", "favorite",
                 "love", "hate", "danger", "excited", "focus", "priority"]

# ── 重要性关键词(复用, 但改为强度演化) ──
IMPORTANCE_POS = ["定理", "证明", "推导", "算法", "架构", "理论", "公式", "定律",
                  "theorem", "proof", "algorithm", "architecture", "理论", "研究",
                  "分析", "方法", "模型", "优化", "benchmark", "实验", "arch",
                  "涂布", "锂", "电池", "coating", "battery", "control"]
IMPORTANCE_NEG = ["delivery", "silent", "nothing", "cron", "schedule", "job_id",
                  "hello", "测试", "检查", "query", "status"]

def score_importance(text):
    """基础重要性评分(信号强度) — 中性偏高, 避免过度剪枝"""
    if not text: return 0.15
    t = text.lower()
    pos = sum(min(3, t.count(kw)) for kw in IMPORTANCE_POS)
    neg = sum(t.count(kw) for kw in IMPORTANCE_NEG)
    base = 0.30 + pos * 0.30 - neg * 0.20   # 基准0.3(中性保留)
    return max(0.05, min(1.0, base))

def emotion_weight(text):
    """情绪加权(杏仁核强化)"""
    if not text: return 1.0
    t = text.lower()
    hits = sum(1 for w in EMOTION_WORDS if w.lower() in t)
    return (EMOTION_WEIGHT - 1) * min(hits, 5) / 5 + 1.0  # 1.0~1.5

def get_sessions(limit=60):
    """读取会话+消息正文 + 时间戳(支持时序重放)"""
    if not os.path.exists(DB_PATH): return []
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute("""
            SELECT s.rowid, s.id, s.title, s.message_count, s.started_at,
                   (SELECT GROUP_CONCAT(substr(m2.content,1,600),' ')
                    FROM (SELECT content FROM messages m2 WHERE m2.session_id=s.id
                          AND m2.role='user' ORDER BY m2.timestamp LIMIT 4) m2)
            FROM sessions s WHERE s.archived=0 AND s.source='weixin'
            ORDER BY s.rowid DESC LIMIT ?
        """, (limit,))
        out = []
        for rowid, sid, title, mc, started, user_msgs in cur.fetchall():
            content = (title or '') + ' ' + (user_msgs or '')
            if not content.strip(): continue
            # 生理适配: 过滤纯 cron/监控噪声会话(如"通联网关健康检查")
            cron_markers = ["通联网关健康", "偏差-方差路由", "okf-daily", "巡检",
                            "每6h更新", "每日新闻早报", "破阵每日", "睡眠巩固",
                            "gateway health", "watchdog", "cron"]
            if any(m in (title or "") for m in cron_markers):
                continue
            out.append({"id": sid, "title": title or content[:40],
                        "content": content[:3000], "created": started or "",
                        "msg_count": mc or 0})
        conn.close()
        # 按时间排序(时序重放按时间先后)
        out.reverse()
        return out
    except Exception as e:
        print(f"⚠️ {e}"); return []

# ── Phase 1: 突触稳态 — 记忆强度连续演化(替代硬剪枝) ──
def consolidate_synaptic(sessions, cycles=NUM_CYCLES):
    """多循环突触稳态巩固: 每轮弱信号衰减, 强信号强化"""
    mems = []
    for s in sessions:
        imp = score_importance(s["content"])
        emo = emotion_weight(s["content"])
        mems.append({**s, "strength": min(1.0, imp * emo),
                     "signals_lost": 0.0, "signals_gain": 0.0})
    # 多循环 NREM-REM
    history = []
    for cyc in range(cycles):
        dropped = 0
        for m in mems:
            old = m["strength"]
            # 突触剪枝: 弱→衰减; 强→长时程增强(保留)
            if old < 0.3:
                m["strength"] *= SYNAPTIC_DECAY   # 弱突触剪枝
            elif old > 0.7:
                m["strength"] = min(1.0, old + PLASTICITY_GAIN)  # 强突触增强
            # 中段: 微调 — 提高中等强度记忆保留率 (AB-SLEEP-02: promote 20%最优)
            else:
                m["strength"] += (min(1.0,old+0.02) - old) * MID_BAND_RETAIN
            m["signals_lost"] += max(0, old - m["strength"])
            m["signals_gain"] += max(0, m["strength"] - old)
            if m["strength"] < 0.05: dropped += 1
        history.append({"cycle": cyc+1, "avg_strength": sum(m["strength"] for m in mems)/max(1,len(mems)),
                        "dropped": dropped})
    # 幸存(强度>0.5) vs 剪枝(生理: 渐进保留, 非极端全丢)
    kept = [m for m in mems if m["strength"] >= 0.35]
    pruned = [m for m in mems if m["strength"] < 0.15]
    return kept, pruned, history

# ── Phase 2: 时序重放 + 时空压缩 (海马SWS) ──
def infer_domain(text):
    t = text.lower()
    domain_keywords = {
        "数学":   ["定理", "证明", "数学", "代数", "拓扑", "公式", "theorem"],
        "AI/推理": ["llm", "模型", "algorithm", "attention", "transformer", "推理", "蒸馏", "agent"],
        "锂电/工程": ["涂布", "锂", "电池", "coating", "battery", "控制", "cpk", "gdt"],
        "运维/系统": ["cron", "gateway", "通联", "health", "config", "部署", "监控"],
        "安全":   ["漏洞", "vuln", "渗透", "cve", "安全", "sandbox", "scan"],
    }
    for dom, kws in domain_keywords.items():
        if any(k in t for k in kws): return dom
    return None  # 无匹配域(不归入"其他", 避免跨域污染)

def replay_temporal(sessions_kept, compress=REPLAY_COMPRESS):
    """按时间顺序把记忆分组→产出具抽象摘要(时空压缩)"""
    # 分组(按时间) → 每组压缩为摘要
    groups = defaultdict(list)
    for m in sessions_kept:
        dom = infer_domain(m.get("content", ""))
        if dom: groups[dom].append(m)
    replays = []
    for dom, items in groups.items():
        if not items: continue
        # 时空压缩: 取每条的关键(前N字)+聚合摘要
        n = max(1, int(len(items) * compress))
        sampled = random.sample(items, min(n, len(items)))
        summary = " | ".join(sel["title"][:20] for sel in sampled)
        replays.append({"domain": dom, "replayed": len(items), "summary": summary[:200]})
    return replays

# ── Phase 3: REM — 跨域新联想生成 ──
def rem_cross_domain(replays):
    """REM: 将不同域抽象概念组合 → 新颖联想"""
    concepts = {
        "数学":   "公理化/严谨推导/边界条件",
        "AI/推理": "token/上下文/注意力/自演化",
        "锂电/工程": "闭环/反馈/过程能力/工艺窗口",
        "运维/系统": "健康监测/自动修复/幂等",
        "安全":   "攻击面/最小权限/纵深防御",
    }
    present = [r["domain"] for r in replays if r["domain"] in concepts]
    links = []
    for i in range(len(present)):
        for j in range(i+1, len(present)):
            d1, d2 = present[i], present[j]
            if d1 != d2 and ("其他" not in d1 and "其他" not in d2):
                links.append(f"🔗 {d1}({concepts[d1]}) ⊕ {d2}({concepts[d2]}) → 潜在创新关联")
    return links[:8]

# ── Phase 4: TMR — 目标记忆定向重激活 ──
def tmr_reactivate(mems, target_keywords, top_n=3):
    """对应生理: 线索触发特定记忆重激活 → 定向增强"""
    scored = []
    for m in mems:
        if any(k.lower() in (m.get("content","") or "").lower() for k in target_keywords):
            scored.append((m["strength"], m["title"], m))
    scored.sort(reverse=True)
    # 重激活 → 增强
    reactivated = []
    for _, title, m in scored[:top_n]:
        old = m["strength"]
        m["strength"] = min(1.0, old + 0.3)  # 定向增强
        reactivated.append({"title": title[:30], "strength": round(old,2), "→": round(m["strength"],2)})
    return reactivated

# ── 主流程 ──
def run_sleep_v3():
    print("💤 改进版睡眠记忆引擎 v3 (基于真实睡眠生理)")
    print("="*60)
    sessions = get_sessions()
    print(f"  读取 {len(sessions)} 个会话(含时序)")

    # 生理: 突触稳态
    print("\n─ Phase 1: 突触稳态巩固(SWS慢波) ─")
    kept, pruned, history = consolidate_synaptic(sessions)
    print(f"  幸存(加强)记忆: {len(kept)}, 剪枝(遗忘)记忆: {len(pruned)}")
    print(f"  多循环强度演化: ", end="")
    print(" → ".join(f"循环{i+1}:均值{s['avg_strength']:.2f}" for i,s in enumerate(history)))

    # 生理: 时序重放(海马)
    print("\n─ Phase 2: 时序重放+时空压缩(SWS尖波) ─")
    replays = replay_temporal(kept)
    print(f"  重放分组: {len(replays)} 个域 (时空压缩摘要)")
    for r in replays[:4]:
        print(f"    📦 {r['domain']}: {r['replayed']}条 → {r['summary'][:60]}")

    # 生理: REM跨域联想
    print("\n─ Phase 3: REM 跨域联想 ─")
    links = rem_cross_domain(replays)
    if links:
        for l in links[:4]: print(f"    {l}")
    else:
        print("    (无跨域联想)")

    # 生理: TMR定向
    print("\n─ Phase 4: TMR 定向重激活(用户近期重点) ─")
    target = ["推理", "蒸馏", "coating", "涂布", "attention", "memory", "记忆", "安全"]
    re_act = tmr_reactivate(kept, target)
    if re_act:
        for r in re_act: print(f"    🔺 {r['title']}: 强度 {r['strength']}→{r['→']}")
    else:
        print("    (无目标记忆)")

    report = {"timestamp": datetime.now().isoformat(), "sessions": len(sessions),
              "kept": len(kept), "pruned": len(pruned), "cycles": history,
              "replays": replays, "rem_links": links}
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    p = f"{OUTPUT_DIR}/sleep_memory_v3_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(p, "w") as f: json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n✅ v3 报告已保存: {p}")

if __name__ == "__main__":
    run_sleep_v3()
