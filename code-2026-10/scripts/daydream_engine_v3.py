#!/usr/bin/env python3
"""
改进版白日梦引擎 v3 — 基于REM睡眠神经机制
==========================================
生理→算法:
  ① 经验重放(海马时序)      → 采样近期高价值会话
  ② 抽象泛化(REM新皮层联想) → 从重放会话提取通用模式
  ③ 跨域新联想(REM自由联想) → 组合不同域概念 → 创新点子
  ④ 情境线索(RETRIEVAL)     → 从记忆库提取当前情境相关模式
  ⑤ 遗忘/巩固(突触稳态)    → 弱关联衰减, 强关联强化
"""
import json, sqlite3, os, sys, random
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher

DB_PATH = "D:/hermes/hermes-data/profiles/qqbot3/state.db"
KB_DIR = "D:/hermes/hermes-data/profiles/qqbot3/knowledge_base"
OUTPUT_DIR = f"{KB_DIR}/audit"

# 参照 sleep_memory 的关键词/域
DOMAIN_CONCEPTS = {
    "数学":   "严谨推导/边界条件/归纳",
    "AI/推理": "上下文压缩/注意力/自演化/蒸馏",
    "锂电/工程": "闭环反馈/过程能力/工艺窗口",
    "运维/系统": "健康监测/自动修复/幂等",
    "安全":   "攻击面/纵深防御/最小权限",
    "病毒学":  "进化/传播/免疫逃逸/分子钟",
}
DOMAIN_KW = {
    "数学":   ["定理", "证明", "数学", "代数", "拓扑", "公式"],
    "AI/推理": ["llm", "模型", "attention", "蒸馏", "推理", "agent", "token", "缓存"],
    "锂电/工程": ["涂布", "锂", "电池", "coating", "cpk", "控制", "gdt"],
    "运维/系统": ["gateway", "health", "config", "部署", "监控", "cron"],
    "安全":   ["漏洞", "渗透", "cve", "安全", "sandbox", "威胁"],
    "病毒学":  ["病毒", "演化", "传播", "免疫", "sir", "分子钟", "病原"],
}

def infer_domain(text):
    t = text.lower()
    for dom, kws in DOMAIN_KW.items():
        if any(k in t for k in kws): return dom
    return None

def get_sessions(limit=100):
    if not os.path.exists(DB_PATH): return []
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute("""
            SELECT s.rowid, s.id, s.title, s.message_count, s.started_at,
                   (SELECT GROUP_CONCAT(substr(m2.content,1,500),' ')
                    FROM (SELECT content FROM messages m2 WHERE m2.session_id=s.id
                          AND m2.role='user' ORDER BY m2.timestamp LIMIT 3) m2)
            FROM sessions s WHERE s.archived=0
            ORDER BY s.rowid DESC LIMIT ?
        """, (limit,))
        out = []
        for rowid, sid, title, mc, started, user_msgs in cur.fetchall():
            content = (title or '') + ' ' + (user_msgs or '')
            if not content.strip(): continue
            dom = infer_domain(content)
            if not dom: continue  # 只处理有明确域的
            out.append({"id": sid, "title": title or content[:40],
                        "content": content[:2500], "domain": dom})
        conn.close()
        return out
    except Exception as e:
        print(f"⚠️ {e}"); return []

# ── Phase 1: 经验重放(REM时序采样) ──
def replay(sessions, k=5):
    """从各域交替采样, 模拟REM时序重放"""
    by_domain = defaultdict(list)
    for s in sessions: by_domain[s["domain"]].append(s)
    replayed = []
    domains = list(by_domain.keys())
    random.shuffle(domains)
    for dom in domains[:k]:
        item = random.choice(by_domain[dom])
        replayed.append({"domain": dom, "title": item["title"][:35],
                         "content": item["content"][:120]})
    return replayed

# ── Phase 2: 抽象泛化(从重放提取通用模式) ──
def abstract(replayed):
    """REM新皮层: 从重放提取跨会话抽象原则(泛化)"""
    concepts = []
    for r in replayed:
        dom = r["domain"]
        if dom in DOMAIN_CONCEPTS:
            concepts.append(DOMAIN_CONCEPTS[dom])
    # 去重+泛化
    seen, gen = set(), []
    for c in concepts:
        if c not in seen:
            seen.add(c); gen.append(c)
    return gen[:5]

# ── Phase 3: 跨域新联想(REM自由联想→创新) ──
def cross_domain_association(domains):
    """组合不同域的核心概念 → 潜在创新点子"""
    if len(domains) < 2: return []
    ideas = []
    doms = list(domains)
    for i in range(len(doms)):
        for j in range(i+1, len(doms)):
            d1, d2 = doms[i], doms[j]
            if d1 == d2: continue
            idea = (f"💡 {d1}({DOMAIN_CONCEPTS[d1]}) ⊕ {d2}({DOMAIN_CONCEPTS[d2]})"
                    f" → 可探索: 用{d1}的方法优化{d2} / 或其组合创新")
            ideas.append(idea)
    return ideas[:6]

# ── Phase 4: 情境检索+巩固(突触稳态) ──
def consolidate_find(concepts, target=["优化", "memory", "安全", "记忆"]):
    """验证: 抽象概念与目标主题的关联(形成可复用洞察)"""
    insights = []
    for c in concepts:
        score = sum(1 for t in target if t.lower() in c.lower())
        if score >= 0:
            insights.append(c)
    return insights

def run_daydream_v3():
    print("⚡ 改进版白日梦引擎 v3 (基于REM睡眠机制)")
    print("="*60)
    sessions = get_sessions(100)
    print(f"  读取 {len(sessions)} 个有语义会话")

    # Phase 1 重放
    print("\n── Phase 1: 经验重放(海马REM) ──")
    replayed = replay(sessions)
    seen_doms = {}
    for r in replayed:
        seen_doms[r["domain"]] = seen_doms.get(r["domain"],0)+1
        print(f"    ▶ [{r['domain']}] {r['title']}")

    # Phase 2 抽象
    print("\n── Phase 2: 抽象泛化(新皮层) ──")
    gen_concepts = abstract(replayed)
    for c in gen_concepts: print(f"    🧠 抽象原则: {c}")

    # Phase 3 跨域联想
    print("\n── Phase 3: 跨域新联想(REM创新) ──")
    present_doms = [r["domain"] for r in replayed]
    ideas = cross_domain_association(set(present_doms))
    if ideas:
        for i in ideas[:4]: print(f"    {i}")
    else:
        print("    (仅单域, 无跨域联想)")

    # Phase 4 巩固
    print("\n── Phase 4: 洞察巩固(突触稳态) ──")
    insights = consolidate_find(gen_concepts)
    for ins in insights[:3]: print(f"    ✅ 可复用: {ins}")

    report = {"timestamp": datetime.now().isoformat(),
              "sessions": len(sessions), "replayed": replayed,
              "concepts": gen_concepts, "ideas": ideas}
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    p = f"{OUTPUT_DIR}/daydream_v3_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(p,"w") as f: json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n✅ v3 白日梦报告: {p}")

if __name__ == "__main__":
    run_daydream_v3()
