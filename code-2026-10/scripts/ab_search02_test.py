# -*- coding: utf-8 -*-
"""
AB-SEARCH-02: MMR lambda 场景自适应 — 固定0.57 vs 自适应(窄0.80/宽0.55)
======================================================================
假设: 自适应λ比固定λ的多样性覆盖率(diversity@5)高15%。
AB-SEARCH-01结论: 固定0.6权重已接近最优, 本测试验证MMR多样性维度。
"""
import sys, io, sqlite3, random
sys.path.insert(0, r"D:/hermes/hermes-data/profiles/mybot/scripts")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from memos_hybrid_search import BM25Search, char_ngrams, jaccard_similarity, mmr_rerank

DB = "D:/hermes/hermes-data/profiles/qqbot3/state.db"

# ── 1. 构建搜索索引 ──
bm = BM25Search(DB)
n = bm.build_from_hermes("qqbot3")
print(f"索引: {n} 条记忆")

# ── 2. 查询集 (基于实际记忆内容的高命中关键词) ──
queries = [
    # 精确查询 (窄场景, 期望高λ保留相关性)
    ("网关健康检查", "narrow"),
    ("通联网关", "narrow"),
    ("watchdog", "narrow"),
    ("新闻早报", "narrow"),
    ("论文推送", "narrow"),
    # 宽泛查询 (宽场景, 期望低λ增加多样性)
    ("研究", "broad"),
    ("优化", "broad"),
    ("分析", "broad"),
    ("报告", "broad"),
    ("任务", "broad"),
]

def diversity_score(results):
    """diversity@5: 5条结果的成对Jaccard不相似度均值"""
    if len(results) < 2:
        return 0.0
    texts = [r["content"][:300] for r in results[:5]]
    sims = []
    for i in range(len(texts)):
        for j in range(i+1, len(texts)):
            s1, s2 = char_ngrams(texts[i]), char_ngrams(texts[j])
            sims.append(jaccard_similarity(s1, s2))
    return 1 - (sum(sims)/len(sims)) if sims else 0.0

def topic_set(results):
    topics = set()
    for r in results[:5]:
        t = r.get("session_title", "")[:20]
        if t: topics.add(t)
    return topics

# ── 3. AB 对比 ──
print("\n" + "="*70)
print("AB-SEARCH-02: MMR λ 固定 vs 自适应")
print("="*70)

rows_fixed, rows_adaptive = [], []
for q, qtype in queries:
    base = bm.search(q, k=15)
    if len(base) < 2:
        continue
    # 固定 λ=0.57
    fixed = mmr_rerank(base, lambda_param=0.57, k=5)
    # 自适应: 窄查询高λ(0.80), 宽查询低λ(0.55)
    lam = 0.80 if qtype == "narrow" else 0.55
    adaptive = mmr_rerank(base, lambda_param=lam, k=5)
    
    df = diversity_score(fixed); da = diversity_score(adaptive)
    tf = topic_set(fixed); ta = topic_set(adaptive)
    rows_fixed.append({"q": q, "div": df, "topics": len(tf)})
    rows_adaptive.append({"q": q, "div": da, "topics": len(ta)})
    print(f"{q[:14]:<16} [{qtype:<6}] 固定λ0.57 div={df:.3f} t={len(tf)} | 自适应 div={da:.3f} t={len(ta)}")

avg_f = sum(r["div"] for r in rows_fixed)/len(rows_fixed)
avg_a = sum(r["div"] for r in rows_adaptive)/len(rows_adaptive)
avg_tf = sum(r["topics"] for r in rows_fixed)/len(rows_fixed)
avg_ta = sum(r["topics"] for r in rows_adaptive)/len(rows_adaptive)

print("\n" + "="*70)
print(f"平均 diversity@5: 固定={avg_f:.3f} 自适应={avg_a:.3f} ({'%+.1f' % ((avg_a-avg_f)*100)}%)")
print(f"平均 主题覆盖:   固定={avg_tf:.1f} 自适应={avg_ta:.1f}")
improve = (avg_a - avg_f) / avg_f * 100 if avg_f else 0
if improve >= 15:
    print(f"✅ H1支持: 自适应λ多样性提升{improve:.1f}% ≥15%")
elif improve > 0:
    print(f"⚠️ 部分支持: 自适应λ提升{improve:.1f}% (未达15%门槛)")
else:
    print(f"❌ H1不支持: 自适应λ多样性{improve:.1f}%, 无提升")

import json, os
os.makedirs("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit", exist_ok=True)
json.dump({
    "experiment": "AB-SEARCH-02", "date": "2026-08-07",
    "avg_diversity_fixed": avg_f, "avg_diversity_adaptive": avg_a,
    "improve_pct": round(improve, 2),
    "rows_fixed": rows_fixed, "rows_adaptive": rows_adaptive,
}, open("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/ab_search02_result.json", "w"), ensure_ascii=False)
print("\n存档: knowledge_base/audit/ab_search02_result.json")
