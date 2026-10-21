# -*- coding: utf-8 -*-
"""
AB-TEMP-01: 记忆半衰期调优 — 30d vs 9.5d
==========================================
概念: 记忆强度随年龄指数衰减, 半衰期=强度减半所需天数
场景: 检索时按"年龄衰减后强度"排序, 看能否召回最新的相关记忆
指标: recall@k (相关记忆是否在衰减后仍在前面), 遗忘覆盖率
"""
import sys, io, sqlite3, math, collections
from datetime import datetime, timezone
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB = "D:/hermes/hermes-data/profiles/qqbot3/state.db"
NOW = datetime(2026,8,2,tzinfo=timezone.utc).timestamp()

HIGHLY = ["定理","证明","涂布","attention","蒸馏","algorithm","memory","安全",
          "coating","模型","research","病毒","演化","agent","MCP"]

# ── 1. 加载真实带时间戳记忆 ──
conn = sqlite3.connect(DB)
rows = conn.execute("""
    SELECT s.title, s.started_at, m.content FROM sessions s
    LEFT JOIN (SELECT session_id, MAX(id) mid FROM messages GROUP BY session_id) mm ON mm.session_id=s.id
    LEFT JOIN messages m ON m.id=mm.mid
    WHERE s.archived=0 AND s.started_at IS NOT NULL
""").fetchall()
conn.close()

mems = []
for title, ts, content in rows:
    text = (title or '') + ' ' + (content or '')
    if not text.strip() or not ts: continue
    age_days = (NOW - ts) / 86400
    label = 1 if any(k.lower() in text.lower() for k in HIGHLY) else 0
    mems.append({"text":text[:800],"age_days":age_days,"label":label,"title":(title or '')[:30]})
mems.sort(key=lambda m:m["age_days"])
print(f"记忆库: {len(mems)} 条 (含时间), 相关{sum(m['label'] for m in mems)}条")
ages = [m["age_days"] for m in mems]
print(f"记忆年龄范围: {min(ages):.0f}~{max(ages):.0f} 天")

# ── 2. 指数衰减弱度 ──
def strength(age_days, half_life):
    return math.exp(-math.log(2)*age_days/half_life)

# ── 3. 检索引擎(年龄衰减后质量排序) ──
def retrieve(mems, half_life, k=20):
    """按 [重要性×衰减强度] 排序取topK"""
    scored = []
    for m in mems:
        imp = min(1.0, 0.1 + sum(m["text"].lower().count(k) for k in HIGHLY)*0.3)
        decay = strength(m["age_days"], half_life)
        scored.append((imp*decay, m))
    scored.sort(reverse=True)
    return scored[:k], scored

# ── 4. AB 对比 ──
print("\n" + "="*66)
print("AB-TEMP-01: 半衰期 30d vs 9.5d (记忆衰减质量)")
print("="*66)

def evaluate_half(mems, half_life, k=20):
    topk, all_sorted = retrieve(mems, half_life, k)
    # recall@k: topK中的相关记忆 / 总相关
    total_rel = sum(m["label"] for m in mems) or 1
    hit_rel = sum(m["label"] for _, m in topk)
    rec = hit_rel/total_rel
    # precision@k
    prec = hit_rel/k
    # 相关记忆的平均强度(衰减后)
    rel_strength = np.mean([strength(m["age_days"], half_life) for m in mems if m["label"]]) or 0
    return rec, prec, hit_rel, rel_strength

# A: 30d
recA, precA, hitA, strA = evaluate_half(mems, 30.0)
# B: 9.5d
recB, precB, hitB, strB = evaluate_half(mems, 9.5)

print(f"\n{'指标':<16} | {'A:30d':>12} | {'B:9.5d':>12} | 差异")
print(f"{'recall@20':<16} | {recA:>12.3f} | {recB:>12.3f} | {(recB-recA)*100:+.1f}pp")
print(f"{'precision@20':<16} | {precA:>12.3f} | {precB:>12.3f} | {(precB-precA)*100:+.1f}pp")
print(f"{'top20相关数':<16} | {hitA:>12} | {hitB:>12}")
print(f"{'相关记忆平均强度':<16} | {strA:>12.3f} | {strB:>12.3f}")

# 遗忘覆盖率: 老化被降权的记忆比例差异
old = [m for m in mems if m["age_days"]>15]
if old:
    b_old = [strength(m["age_days"],9.5) for m in old]
    a_old = [strength(m["age_days"],30) for m in old]
    print(f"\n  15天以上旧记忆({len(old)}条)强度: 30d={np.mean(a_old):.3f} vs 9.5d={np.mean(b_old):.3f}")

print("\n" + "="*66)
if recB > recA and precB >= precA:
    print("✅ H1支持: 9.5d半衰期 recall/precision 更高")
elif recB > recA:
    print("🟡 部分支持: 9.5d召回更高但precision需权衡")
elif abs(recB-recA) < 0.01:
    print("⚠️ 差异不显著: 半衰期影响小")
else:
    print("❌ H1不支持: 30d更好, 9.5d过度遗忘损失召回")

import json, os
os.makedirs("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit", exist_ok=True)
json.dump({
    "experiment":"AB-TEMP-01","date":"2026-08-02","memories":len(mems),
    "A_30d":{"recall":recA,"precision":precA,"strength":strA},
    "B_9.5d":{"recall":recB,"precision":precB,"strength":strB},
}, open("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/ab_temp01_result.json","w"), ensure_ascii=False)
print(f"\n存档: knowledge_base/audit/ab_temp01_result.json")
