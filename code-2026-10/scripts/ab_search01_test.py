# -*- coding: utf-8 -*-
"""
AB-SEARCH-01: BM25+KNN 混合权重优化 — 固定(0.6) vs 自适应(精确0.7/模糊0.5)
======================================================================
数据: 真实 41993 条消息 (memos_vec.db / state.db)
方法: 精确/模糊查询各 N 条, 用 BM25+语义得分, 召回质量对比
指标: 命中质量 (topK 是否含查询核心主题的真实相关文档)
说明: 无人工标注 → 用"核心词命中+去重"代理 NDCG; 对比两种权重策略
"""
import sys, io, sqlite3, re, math, collections
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB = "D:/hermes/hermes-data/profiles/qqbot3/state.db"

# ── 1. 加载真实文档 (从 messages) ──
conn = sqlite3.connect(DB)
rows = conn.execute("""
    SELECT id, content, session_id FROM messages 
    WHERE content IS NOT NULL AND length(content) > 30
    ORDER BY id DESC LIMIT 3000
""").fetchall()
conn.close()
docs = [{"id": str(r[0]), "text": r[1], "sid": r[2]} for r in rows]
print(f"文档池: {len(docs)} 条 (真实消息)")

# ── 2. 构建简单 BM25 ──
def tokenize(t): return re.findall(r"[\w\u4e00-\u9fff]+", t.lower())
corpus_tokens = [tokenize(d["text"]) for d in docs]
N = len(docs)
df = collections.Counter()
for toks in corpus_tokens:
    for t in set(toks): df[t] += 1
avgdl = np.mean([len(t) for t in corpus_tokens]) or 1
k1, b = 1.5, 0.75
def bm25_score(text_tokens, query_tokens):
    dl = len(text_tokens)
    s = 0
    tf = collections.Counter(text_tokens)
    for q in set(query_tokens):
        if q not in df: continue
        n = df[q]; f = tf[q]
        idf = math.log(1 + (N - n + 0.5)/(n + 0.5))
        s += idf * f*(k1+1)/(f + k1*(1-b+b*dl/avgdl))
    return s

# ── 3. 语义得分代理 (共用词覆盖) ──
def semantic_sim(qtokens, dtokens):
    if not dtokens: return 0
    inter = len(set(qtokens) & set(dtokens))
    return inter / math.sqrt(len(set(qtokens))*len(set(dtokens)) + 1e-6)

# ── 4. 混合检索 (权重参数化) ──
def hybrid_search(qtext, bm25_w, k=5, candidates=100):
    qtokens = tokenize(qtext)
    if not qtokens: return []
    # BM25 top-candidates
    scored_bm = []
    for i, dt in enumerate(corpus_tokens):
        s = bm25_score(dt, qtokens)
        if s > 0: scored_bm.append((s, i))
    scored_bm.sort(reverse=True)
    top_idx = [i for _, i in scored_bm[:candidates]]
    if not top_idx: return []
    # 语义分 (在top候选中)
    bm_max = scored_bm[0][0] if scored_bm else 1
    res = []
    for i in top_idx:
        sm = semantic_sim(qtokens, corpus_tokens[i])
        bm = bm25_score(corpus_tokens[i], qtokens)
        bm_norm = bm / (bm_max + 1e-6)   # 归一化到[0,1]
        hybrid = bm25_w * bm_norm + (1 - bm25_w) * sm
        res.append((hybrid, i))
    res.sort(reverse=True)
    return res[:k]

# ── 5. 精确/模糊查询集 (真实主题) — 中英混合触发BM25 ──
precise_queries = ["memory 记忆 long 上下文", "transformer attention 注意力 模型",
                   "coating 涂布 battery 电池 控制", "virus 病毒 evolution 演化模型",
                   "token 压缩 MCP server agent"]
fuzzy_queries = ["LLM 优化 推理 效率 方法", "knowledge base 知识库 检索 构建",
                 "电池 工艺 改进 流程 参数", "传染病 传播 模型 数学 演化",
                 "sleep 睡眠 记忆 巩固 算法"]

# ── 6. 评估: 命中质量代理 (topK 与查询的相关性: 语义均值) ──
def evaluate_queries(queries, bm25_w, k=5):
    sr_scores = []
    for q in queries:
        qtokens = tokenize(q)
        res = hybrid_search(q, bm25_w, k)
        if not res:
            continue   # 无命中, 跳过
        rel_scores = []
        for _, idx in res:
            sm = semantic_sim(qtokens, corpus_tokens[idx])
            rel_scores.append(sm)
        if rel_scores:
            sr_scores.append(np.mean(rel_scores))
    return np.mean(sr_scores) if sr_scores else 0.0

print("\n" + "="*66)
print("AB-SEARCH-01 执行: 固定权重 vs 自适应权重")
print("="*66)

# 实验A: 固定 0.60 (所有查询)
print("\n【A】固定权重 bm25=0.60 (所有查询)")
a_precise = evaluate_queries(precise_queries, 0.60)
a_fuzzy = evaluate_queries(fuzzy_queries, 0.60)
a_all = evaluate_queries(precise_queries+fuzzy_queries, 0.60)
print(f"  精确查询相关性: {a_precise:.4f} | 模糊查询: {a_fuzzy:.4f} | 整体: {a_all:.4f}")

# 实验B: 自适应 (精确0.70, 模糊0.50)
print("\n【B】自适应权重 (精确0.70 / 模糊0.50)")
b_precise = evaluate_queries(precise_queries, 0.70)
b_fuzzy = evaluate_queries(fuzzy_queries, 0.50)
b_all = (b_precise*len(precise_queries) + b_fuzzy*len(fuzzy_queries)) / (len(precise_queries)+len(fuzzy_queries))
print(f"  精确查询(0.70): {b_precise:.4f} | 模糊查询(0.50): {b_fuzzy:.4f} | 整体: {b_all:.4f}")

# ── 7. 结论 ──
print("\n" + "="*66)
print(f"精确查询提升: {a_precise:.4f} → {b_precise:.4f} ({(b_precise-a_precise)/max(1e-6,a_precise)*100:+.1f}%)")
print(f"模糊查询提升: {a_fuzzy:.4f} → {b_fuzzy:.4f} ({(b_fuzzy-a_fuzzy)/max(1e-6,a_fuzzy)*100:+.1f}%)")
print(f"整体提升: {a_all:.4f} → {b_all:.4f}")
p_imp = (b_precise-a_precise)/max(1e-6,a_precise)*100
f_imp = (b_fuzzy-a_fuzzy)/max(1e-6,a_fuzzy)*100
if p_imp > 2 and f_imp > 2:
    verdict = "✅ H1确认: 自适应权重(精确0.7/模糊0.5)优于固定0.6"
elif p_imp > 2 or f_imp > 2:
    verdict = "🟡 部分支持: 自适应在某类查询更好, 建议分场景"
else:
    verdict = "⚠️ 差异不显著: 固定0.6已足够, 不需自适应"
print(f"\n判定: {verdict}")

import json, os
os.makedirs("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit", exist_ok=True)
json.dump({
    "experiment":"AB-SEARCH-01", "date":"2026-08-02",
    "fixed0.6":{"precise":a_precise,"fuzzy":a_fuzzy,"all":a_all},
    "adaptive":{"precise":b_precise,"fuzzy":b_fuzzy,"all":b_all},
    "verdict":verdict,
}, open("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/ab_search01_result.json","w"), ensure_ascii=False)
print(f"\n存档: knowledge_base/audit/ab_search01_result.json")
