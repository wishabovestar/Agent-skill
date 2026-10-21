# -*- coding: utf-8 -*-
"""OmniRoute 优化前后对比 + 7月token消耗汇总"""
import sys, io, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, "D:/hermes/hermes-data/profiles/qqbot3/scripts")
import bias_variance_router as ov

print("="*66)
print("OmniRoute 优化前后 A/B 对比 + 7月 token 消耗")
print("="*66)

router = ov.BiasVarianceRouter()

# ── 真实7月风格工作负载 (广泛任务) ──
TASKS = [
    ('code_gen',0.3,0.2,0.3,0.6,2000),('code_gen',0.5,0.4,0.2,0.7,4000),
    ('code_gen',0.7,0.6,0.3,0.8,6000),('code_review',0.5,0.5,0.3,0.7,4000),
    ('code_review',0.4,0.4,0.3,0.6,3000),('theorem_proof',0.9,0.9,0.4,0.8,9000),
    ('theorem_proof',0.85,0.85,0.5,0.7,8000),('data_analysis',0.6,0.5,0.5,0.5,6000),
    ('svg_gen',0.3,0.2,0.8,0.4,1500),('domain_knowledge',0.5,0.5,0.8,0.5,3500),
    ('tool_calling',0.3,0.3,0.5,0.6,2000),('planning',0.7,0.7,0.4,0.7,7000),
    ('code_gen',0.4,0.3,0.3,0.7,3000),('svg_gen',0.2,0.1,0.9,0.3,1000),
]
TASKS_30 = TASKS * 2 + TASKS[:2]  # 30次

# ── 对比: cost_aware OFF (模拟优化前) vs ON (优化后) ──
def simulate(cost_aware, force_deep=False):
    sched = collections.Counter(); tokens = collections.Counter(); cost = collections.Counter()
    for tt, c, r, ch, s, b in TASKS_30:
        t = ov.TaskProfile(tt, complexity=c, reasoning_depth=r, chinese_ratio=ch,
                           stability_required=s, budget_tokens=b)
        rec = router.route(t, top_k=1, cost_aware=cost_aware)[0]
        sched[rec["model"]] += 1
        tokens[rec["model"]] += b
        cost[rec["model"]] += rec["cost_estimate"]
    return sched, tokens, cost

# 优化前 (cost_aware=False → 原逻辑)
sched0, tok0, cost0 = simulate(False)
# 优化后 (cost_aware=True + 深推理)
sched1, tok1, cost1 = simulate(True)

total0 = sum(cost0.values()); total1 = sum(cost1.values())
saving = (total0-total1)/total0*100 if total0 else 0

print("\n【优化前】(忽略成本, 纯得分)") 
for m,c in sched0.most_common():
    print(f"  {m:<20} {c:>2}次 | ${cost0[m]:.2f}")
print(f"  总成本: ${total0:.2f} | 总token: {sum(tok0.values()):,}")

print("\n【优化后】(成本感知 + 深推理专用)")
for m,c in sched1.most_common():
    print(f"  {m:<20} {c:>2}次 | ${cost1[m]:.2f}")
print(f"  总成本: ${total1:.2f} | 总token: {sum(tok1.values()):,}")

print(f"\n🟢 成本节省: {saving:.1f}% (${total0:.2f} → ${total1:.2f})")

# ── 深推理专用模型验证 ──
print("\n【深推理】theorem_proof(复杂度0.9, 推理0.9):")
t = ov.TaskProfile("theorem_proof", complexity=0.9, reasoning_depth=0.9, budget_tokens=9000)
print(f"  优化前推荐: {router.route(t,1,False)[0]['model']}")
print(f"  优化后推荐: {router.route(t,1,True)[0]['model']}")

# 存档
os = __import__('os')
os.makedirs("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit", exist_ok=True)
json.dump({
    "before": {"cost": round(total0,2), "sched": dict(sched0)},
    "after": {"cost": round(total1,2), "sched": dict(sched1)},
    "saving_pct": round(saving,1),
}, open("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/omniroute_opt_compare.json","w"), indent=2, ensure_ascii=False)
print("\n✅ 存档: knowledge_base/audit/omniroute_opt_compare.json")
