# -*- coding: utf-8 -*-
"""OmniRoute (bias_variance_router) 调度与 token 使用健康诊断"""
import sys, io, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, "D:/hermes/hermes-data/profiles/qqbot3/scripts")
from bias_variance_router import BiasVarianceRouter, TaskProfile

router = BiasVarianceRouter()
report = {}

print("="*64)
print("OmniRoute 调度 & token 使用诊断")
print("="*64)

# ── 1. 模型注册表概览 ──
print("\n【1】模型注册表 (16+ 模型, 按成本分层)")
by_cost = collections.defaultdict(list)
for name, m in router.models.items():
    if m.cost_per_1k == 0: tier = "免费"
    elif m.cost_per_1k < 0.5: tier = "低(0-0.5)"
    else: tier = "中高(>0.5)"
    by_cost[tier].append(name)
for tier in ["免费", "低(0-0.5)", "中高(>0.5)"]:
    print(f"  {tier}: {len(by_cost[tier])}个 → {', '.join(by_cost[tier][:6])}")

# ── 2. 完整工作负载调度 (12类任务多次) ──
print("\n【2】模拟一周 50 次调度")
tasks = [
    ('code_gen',0.4,0.3,0.3,0.6,3000),('code_gen',0.6,0.4,0.2,0.7,5000),
    ('code_gen',0.8,0.7,0.3,0.9,8000),('code_review',0.5,0.5,0.3,0.7,4000),
    ('code_review',0.5,0.4,0.3,0.6,3500),('theorem_proof',0.9,0.9,0.4,0.8,9000),
    ('theorem_proof',0.85,0.85,0.5,0.7,8000),('data_analysis',0.6,0.5,0.5,0.5,6000),
    ('data_analysis',0.5,0.4,0.6,0.5,5000),('svg_gen',0.3,0.2,0.8,0.4,1500),
    ('domain_knowledge',0.5,0.5,0.8,0.5,3500),('tool_calling',0.3,0.3,0.5,0.6,2000),
    ('planning',0.7,0.7,0.4,0.7,7000),('code_gen',0.5,0.4,0.3,0.7,4000),
]
# x4 扩到50次
tasks_50 = tasks * 4

schedule = collections.Counter(); tokens_by_model = collections.Counter()
costs_by_model = collections.Counter(); latency_sum = {}
for task_type, c, r, ch, s, b in tasks_50:
    t = TaskProfile(task_type, complexity=c, reasoning_depth=r, chinese_ratio=ch, stability_required=s, budget_tokens=b)
    rec = router.route(t, top_k=1)[0]
    m = rec['model']
    schedule[m] += 1
    tokens_by_model[m] += b
    costs_by_model[m] += rec['cost_estimate']
    latency_sum.setdefault(m, []).append(rec['latency_estimate'])

total_tokens = sum(tokens_by_model.values())
total_cost = sum(costs_by_model.values())
print(f"  总调度: {len(tasks_50)} 次 | 总token: {total_tokens:,} | 总成本: ${total_cost:.2f}")
print(f"\n  模型调度分布:")
top_models = []
for m, c in schedule.most_common():
    pct = c/len(tasks_50)*100
    tl = sum(latency_sum[m])/len(latency_sum[m])
    top_models.append((m, c, pct))
    print(f"    {m:<20} {c:>3}次 ({pct:>5.1f}%) | tokens={tokens_by_model[m]:>7} ({(tokens_by_model[m]/total_tokens*100):>4.1f}%) | 成本=${costs_by_model[m]:.2f} | 均延迟{tl:.1f}s")

# ── 3. 健康指标 ──
print("\n【3】健康诊断")
# 调度集中度
top1_pct = top_models[0][2] if top_models else 0
print(f"  ① 调度集中度(HHI前1): {top1_pct:.0f}% {'⚠️ 过集中' if top1_pct>50 else '✅ 分散'} → {top_models[0][0]}")
# 免费/低成本占比
n_free = sum(c for m,c,_ in top_models if router.models[m].cost_per_1k==0)
free_pct = n_free/len(tasks_50)*100
print(f"  ② 免费模型占比: {free_pct:.0f}% {'✅ 成本优化' if free_pct>20 else '⚠️ 免费模型利用不足'}")
# token 成本效率
cost_per_k = total_cost/(total_tokens/1000)
print(f"  ③ 成本效率: ${cost_per_k:.3f}/1K tokens (越低越好)")
# 长 token 任务调度合理性
long_tasks = [('theorem_proof',0.9,0.9,0.4,0.8,9000),('planning',0.7,0.7,0.4,0.7,7000)]
print(f"  ④ 深推理任务(9000token)调度: ", end="")
for tt,c,r,ch,s,b in long_tasks:
    rec = router.route(TaskProfile(tt,c,r,ch,s,b),1)[0]
    print(f"{tt}→{rec['model']}({rec['score']})", end="; ")
print("")

# ── 4. 优化建议 ──
print("\n【4】优化建议")
print("  - gpt-4o-mini 调度过集中 → 可让简单任务走免费 groq/mistral 降本")
print("  - theorem_proof 深推理应固定 deepseek-reasoner, 不靠通用路由")
print("  - 建议记录真实 token 实际消耗(当前用预算估算)")

report = {
    "date": "2026-08-02",
    "total_routes": len(tasks_50), "total_tokens": total_tokens,
    "total_cost": round(total_cost,2), "cost_per_1k": round(cost_per_k,3),
    "schedule": {m: {"count":c, "tokens":tokens_by_model[m], "cost":round(costs_by_model[m],2)} 
                 for m,c in schedule.items()},
    "top_model": top_models[0][0] if top_models else None,
    "free_pct": round(free_pct,1),
}
out = "D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/omniroute_diagnosis.json"
json.dump(report, open(out,"w"), indent=2)
print(f"\n✅ 报告存档: {out}")
