# -*- coding: utf-8 -*-
"""
AB-TEMP-02: 压缩阶段边界优化 — stage边界 7/30d vs 3/10/30d
==========================================================
概念: 记忆按年龄划分压缩阶段, 阶段越老压缩程度越高(细节丢失)
场景: 对比两种阶段边界, 看哪种能减少"过早压缩"(相关记忆在活跃期就被压到旧阶段)
假设 H1: 自适应边界(3/10/30d)能减少过早压缩 — 更多相关记忆停留在高保真阶段
指标:
  stage_distribution   各阶段记忆占比 (fresh/medium/mature/old)
  压缩前召回率         相关记忆在压缩前的平均保真度(加权保留率) — 越高越好
依赖: AB-TEMP-01 (半衰期30d保留), qqbot3 记忆库积累>30天数据
"""
import sys, io, sqlite3, math, os, json, collections
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB = "D:/hermes/hermes-data/profiles/qqbot3/state.db"
NOW = datetime.now(timezone.utc).timestamp()

HIGHLY = ["定理", "证明", "涂布", "attention", "蒸馏", "algorithm", "memory", "安全",
          "coating", "模型", "research", "病毒", "演化", "agent", "MCP"]

# ── 1. 加载真实带时间戳记忆 (与AB-TEMP-01同源) ──
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
    if age_days < 0: continue
    label = 1 if any(k.lower() in text.lower() for k in HIGHLY) else 0
    mems.append({"text": text[:800], "age_days": age_days, "label": label, "title": (title or '')[:30]})
mems.sort(key=lambda m: m["age_days"])
print(f"记忆库: {len(mems)} 条 (含时间), 相关{sum(m['label'] for m in mems)}条")
ages = [m["age_days"] for m in mems]
print(f"记忆年龄范围: {min(ages):.0f}~{max(ages):.0f} 天 (跨度 {max(ages)-min(ages):.0f} 天)")
print(f">30天数据可用: {'✅' if max(ages) > 30 else '❌'}")

# ── 2. 压缩阶段定义 ──
# A (当前): 边界 7/30 → [fresh<7, medium 7-30, old>30]
# B (候选): 边界 3/10/30 → [fresh<3, medium 3-10, mature 10-30, old>30]
VARIANT_A = [(0, 7), (7, 30), (30, float('inf'))]
VARIANT_B = [(0, 3), (3, 10), (10, 30), (30, float('inf'))]
STAGE_NAMES = {0: "fresh", 1: "medium", 2: "mature", 3: "old"}
# 各阶段保真度(压缩后保留比例): fresh=1.0, medium=0.85, mature=0.70, old=0.50
RETENTION = {0: 1.0, 1: 0.85, 2: 0.70, 3: 0.50}

def stage_of(age, boundaries):
    for i, (lo, hi) in enumerate(boundaries):
        if lo <= age < hi:
            return i
    return len(boundaries) - 1

# ── 3. 指标计算 ──
def evaluate(boundaries, name):
    dist = collections.Counter(stage_of(m["age_days"], boundaries) for m in mems)
    n = len(mems) or 1
    rel_mems = [m for m in mems if m["label"]]
    # 压缩前召回率: 相关记忆平均保真度 (1.0 = 全部停留在fresh阶段)
    recall_before = sum(RETENTION[stage_of(m["age_days"], boundaries)] for m in rel_mems) / (len(rel_mems) or 1)
    # 过早压缩率: 相关记忆落入最老阶段的比例 (压缩最狠)
    old_stage = len(boundaries) - 1
    premature = sum(1 for m in rel_mems if stage_of(m["age_days"], boundaries) == old_stage) / (len(rel_mems) or 1)
    print(f"\n── {name} (边界: {boundaries}) ──")
    print(f"  stage分布: " + ", ".join(f"{STAGE_NAMES.get(i, i)}={dist.get(i,0)}条({dist.get(i,0)/n*100:.1f}%)" for i in sorted(dist)))
    print(f"  压缩前召回率(相关记忆平均保真度): {recall_before:.4f}")
    print(f"  相关记忆过早压缩率(落入最老阶段): {premature*100:.1f}%")
    return {"stage_distribution": {STAGE_NAMES.get(i, str(i)): dist.get(i, 0) for i in sorted(dist)},
            "recall_before_compress": recall_before, "premature_rate": premature}

print("\n" + "="*70)
print("AB-TEMP-02: 压缩阶段边界 A(7/30d) vs B(3/10/30d)")
print("="*70)
resA = evaluate(VARIANT_A, "A: 当前 7/30d")
resB = evaluate(VARIANT_B, "B: 候选 3/10/30d")

print("\n" + "="*70)
diff = resB["recall_before_compress"] - resA["recall_before_compress"]
print(f"压缩前召回率: A={resA['recall_before_compress']:.4f} B={resB['recall_before_compress']:.4f} (Δ{diff*100:+.2f}pp)")
if resB["recall_before_compress"] > resA["recall_before_compress"] + 0.005:
    print("✅ H1支持: 自适应边界(3/10/30d)减少过早压缩, 压缩前召回率更高")
elif abs(diff) <= 0.005:
    print("⚠️ 差异不显著: 边界调整对压缩前召回率影响小")
else:
    print("❌ H1不支持: 当前边界(7/30d)更优")

os.makedirs("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit", exist_ok=True)
json.dump({
    "experiment": "AB-TEMP-02", "date": datetime.now().isoformat(),
    "memories": len(mems), "age_span_days": round(max(ages)-min(ages), 1),
    "A_7_30": resA, "B_3_10_30": resB,
    "conclusion": "H1支持" if resB["recall_before_compress"] > resA["recall_before_compress"] + 0.005 else ("差异不显著" if abs(diff) <= 0.005 else "H1不支持"),
}, open("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/ab_temp02_result.json", "w"), ensure_ascii=False)
print("\n存档: knowledge_base/audit/ab_temp02_result.json")
