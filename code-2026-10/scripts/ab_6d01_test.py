# -*- coding: utf-8 -*-
"""
AB-6D-01: 6D 话题评分权重优化 — 均匀权重 vs 优化权重
===================================================
基于 memos_vec.db 真实记忆, 实现6维评分:
  frequency(频次) / relevance(相关性) / diversity(多样性)
  recency(时效) / consolidation(巩固度) / conceptual_depth(概念深度)
对比均匀权重(0.167) vs 优化权重(freq=0.2,div=0.2,rel=0.15,rec=0.15,con=0.15,dep=0.15)
假设: 优化权重使6D话题排序相关性提升20% (rank_correlation)
"""
import sys, io, sqlite3, re, math
from collections import Counter, defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB = "D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/memos_vec.db"
conn = sqlite3.connect(DB)

# ── 1. 提取记忆 + 话题(用session_title聚类) ──
rows = conn.execute("SELECT content, session_title, created_at FROM memos_body LIMIT 3000").fetchall()
conn.close()

memories = []
for content, title, created in rows:
    if not content or not title:
        continue
    memories.append({"content": content[:500], "title": title[:40], "created": created})

# 话题 = 按session_title聚合
topics = defaultdict(list)
for m in memories:
    topics[m["title"]].append(m)
print(f"记忆: {len(memories)} 条, 话题: {len(topics)} 个")

# ── 2. 6维评分函数 ──
def score_frequency(topic_mems, all_mems):
    return len(topic_mems) / max(1, len(all_mems))

def score_relevance(topic_mems, all_mems):
    # 与全部记忆的平均内容重叠度(字符n-gram Jaccard)
    ngrams_all = set()
    for m in all_mems[:500]:
        ngrams_all |= set(m["content"][i:i+3] for i in range(len(m["content"])-2))
    ngrams_topic = set()
    for m in topic_mems:
        ngrams_topic |= set(m["content"][i:i+3] for i in range(len(m["content"])-2))
    if not ngrams_all or not ngrams_topic:
        return 0.0
    return len(ngrams_topic & ngrams_all) / len(ngrams_topic)

def score_diversity(topic_mems, all_mems):
    # 话题内多样性: 不同内容模式的分布(用长度分布近似)
    lengths = [len(m["content"]) for m in topic_mems]
    if not lengths:
        return 0.0
    buckets = Counter(l // 50 for l in lengths)
    return len(buckets) / max(1, len(lengths))

def score_recency(topic_mems):
    if not topic_mems or all(not m["created"] for m in topic_mems):
        return 0.5
    # 最近记忆占比 (created字段解析为时间戳, 简单用index近似)
    recent = sum(1 for m in topic_mems if m["created"])
    return recent / len(topic_mems)

def score_consolidation(topic_mems):
    # 跨会话巩固度: 话题内平均记忆数
    return min(1.0, len(topic_mems) / 10.0)

def score_conceptual_depth(topic_mems):
    # 概念深度: 内容中专业术语密度
    terms = ["算法","模型","优化","分析","系统","网络","数据","研究","测试","架构"]
    total = sum(len(m["content"]) for m in topic_mems)
    hits = sum(sum(m["content"].count(t) for t in terms) for m in topic_mems)
    return min(1.0, hits / max(1, total / 100))

# ── 3. 话题排序对比 ──
def rank_topics(weights):
    scored = []
    for title, mems in topics.items():
        if len(mems) < 2:
            continue
        s = (weights["frequency"] * score_frequency(mems, memories) +
             weights["relevance"] * score_relevance(mems, memories) +
             weights["diversity"] * score_diversity(mems, memories) +
             weights["recency"] * score_recency(mems) +
             weights["consolidation"] * score_consolidation(mems) +
             weights["conceptual_depth"] * score_conceptual_depth(mems))
        scored.append((title, s))
    scored.sort(key=lambda x: -x[1])
    return [t for t, _ in scored[:20]]

WEIGHTS_EQUAL = {"frequency": 1/6, "relevance": 1/6, "diversity": 1/6,
                 "recency": 1/6, "consolidation": 1/6, "conceptual_depth": 1/6}
WEIGHTS_OPT = {"frequency": 0.2, "relevance": 0.15, "diversity": 0.2,
               "recency": 0.15, "consolidation": 0.15, "conceptual_depth": 0.15}

rank_equal = rank_topics(WEIGHTS_EQUAL)
rank_opt = rank_topics(WEIGHTS_OPT)

# ── 4. 评估: 排序相关性 + 话题多样性覆盖率 ──
def rank_correlation(r1, r2):
    """Kendall tau近似: 交集排序一致性"""
    s1 = {t: i for i, t in enumerate(r1)}
    s2 = {t: i for i, t in enumerate(r2)}
    common = set(s1) & set(s2)
    if len(common) < 2:
        return 0.0
    concordant = discordant = 0
    cl = list(common)
    for i in range(len(cl)):
        for j in range(i+1, len(cl)):
            a, b = cl[i], cl[j]
            if (s1[a]-s1[b]) * (s2[a]-s2[b]) > 0:
                concordant += 1
            else:
                discordant += 1
    return (concordant - discordant) / (concordant + discordant)

tau = rank_correlation(rank_equal, rank_opt)
overlap = len(set(rank_equal) & set(rank_opt)) / 20

print("\n" + "="*70)
print("AB-6D-01: 6D评分权重 均匀 vs 优化")
print("="*70)
print(f"\n均匀权重 Top10: {rank_equal[:10]}")
print(f"优化权重 Top10: {rank_opt[:10]}")
print(f"\nKendall τ = {tau:.3f}")
print(f"Top20 重叠率 = {overlap:.1%}")

print("\n" + "="*70)
if tau > 0.7:
    print("✅ 两权重方案排序高度一致 → 权重影响不大, 优化权重无显著增益")
elif tau > 0.4:
    print(f"⚠️ 中等相关(τ={tau:.2f}) → 权重有影响但需验证是否正向")
else:
    print(f"✅ 排序差异显著(τ={tau:.2f}) → 权重方案确实改变话题排序, 需人工评估哪个更优")

import json, os
os.makedirs("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit", exist_ok=True)
json.dump({
    "experiment": "AB-6D-01", "date": "2026-08-07",
    "kendall_tau": tau, "overlap": overlap,
    "rank_equal": rank_equal, "rank_opt": rank_opt,
}, open("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/ab_6d01_result.json", "w"), ensure_ascii=False)
print("\n存档: knowledge_base/audit/ab_6d01_result.json")
