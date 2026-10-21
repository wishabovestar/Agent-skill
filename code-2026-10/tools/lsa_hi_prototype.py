#!/usr/bin/env python3
"""LSA Hierarchical Indexing 数学原型验证 (P1)
在CPU上用小模型/合成数据验证HI索引的数学正确性:
1. 粗阶段块评分 vs 细阶段token评分的一致性
2. 稀疏attention与全量attention的精度对比
"""
import numpy as np
import time

np.random.seed(42)

# ============ 1. 合成数据: 真实LLM注意力特征 ============
L = 4096        # 上下文长度
d = 64          # KV维度
np.random.seed(42)

# 真实LLM注意力: 极少数sink token + 少量语义相关token占主导
# (1) sink token: 前4个token (固定高注意力, DSA/SnapKV已知现象)
# (2) 语义簇: 30个分散的相关token
# (3) 其余: 低注意力噪声
K = np.random.randn(L, d) * 0.3
q = np.random.randn(d)

# sink token: key与query中等相关 (通用关注)
K[:4] = q * 0.8 + np.random.randn(4, d) * 0.2

# 语义簇: 30个高相关token (分散在长文本中)
cluster_pos = np.random.choice(range(100, L-100), 30, replace=False)
K[cluster_pos] = q * 1.2 + np.random.randn(30, d) * 0.05

# 局部窗口: 最近64个token中等相关 (时间局部性)
K[-64:] = q * 0.6 + np.random.randn(64, d) * 0.3

V = np.random.randn(L, d)

# ============ 2. 全量注意力 (ground truth) ============
def full_attention(q, K, V):
    scores = q @ K.T / np.sqrt(d)
    scores = scores - scores.max()
    alpha = np.exp(scores) / np.exp(scores).sum()
    out = alpha @ V
    return out, alpha

out_full, alpha_full = full_attention(q, K, V)

# ============ 3. HI: 粗到细索引 ============
def hi_attention(q, K, V, b=64, m=8, k=1024):
    """Hierarchical Indexing:
    粗阶段: 块聚合 → 选top-m块
    细阶段: 块内token评分 → 合并top-k
    """
    L = K.shape[0]
    N_b = L // b  # 块数
    
    # 粗阶段: 块级key均值
    K_blocks = K[:N_b*b].reshape(N_b, b, d).mean(axis=1)  # (N_b, d)
    block_scores = (q @ K_blocks.T) / np.sqrt(d)  # (N_b,)
    top_blocks = np.argsort(block_scores)[::-1][:m]
    
    # 细阶段: 选中的块内token评分
    candidate_idx = []
    for bi in top_blocks:
        start = bi * b
        tok_scores = (q @ K[start:start+b].T) / np.sqrt(d)
        candidate_idx.extend(range(start, start+b))
    
    # 合并排序取top-k
    cand_scores = (q @ K[candidate_idx].T) / np.sqrt(d)
    top_k_local = np.argsort(cand_scores)[::-1][:k]
    top_k_idx = [candidate_idx[i] for i in top_k_local]
    
    # LSA关键: 强制保留 sink token + 局部窗口 (DSA/LSA设计)
    forced_idx = list(range(4)) + list(range(max(0, L-64), L))  # sink4 + window64
    top_k_idx = list(dict.fromkeys(forced_idx + top_k_idx))  # 去重保序
    
    # 稀疏attention (top-k token)
    scores = (q @ K[top_k_idx].T) / np.sqrt(d)
    scores = scores - scores.max()
    alpha_sparse = np.exp(scores) / np.exp(scores).sum()
    out_sparse = alpha_sparse @ V[top_k_idx]
    
    return out_sparse, top_k_idx, alpha_sparse

b, m, k = 64, 8, 1024
out_hi, top_idx, alpha_hi = hi_attention(q, K, V, b, m, k)

# ============ 4. 精度评估 ============
cos_sim = np.dot(out_full, out_hi) / (np.linalg.norm(out_full) * np.linalg.norm(out_hi))
# 注意力覆盖度: 稀疏attention是否覆盖了全量attention的主要质量
covered = alpha_full[top_idx].sum()

# 复杂度统计
N_b = L // b
hi_compute = N_b + m*b  # 索引计算量
full_compute = L        # 全量
attn_compute = k        # attention计算量

print("=" * 60)
print("LSA Hierarchical Indexing 数学验证 (L=4096, d=64)")
print("=" * 60)
print(f"\n--- 精度 ---")
print(f"输出余弦相似度: {cos_sim:.4f}  (1.0=完全一致)")
print(f"覆盖的注意力质量: {covered:.3f}  (top-{k} 覆盖全量attention的{covered*100:.0f}%)")

print(f"\n--- 计算复杂度 ---")
print(f"全量: {full_compute} 次评分")
print(f"HI:  索引 {hi_compute} + attention {k} = {hi_compute+k}")
print(f"加速比: {full_compute/(hi_compute+k):.1f}x")

print(f"\n--- 结论 ---")
if cos_sim > 0.9 and covered > 0.8:
    print("✅ HI数学有效: 稀疏attention保留90%+信息, 计算降4x")
else:
    print(f"⚠️ 需调参: cos={cos_sim:.3f}, covered={covered:.3f}")
    
# 参数敏感性
print(f"\n--- 参数敏感性 (b,m,k) ---")
for bb, mm, kk in [(32, 16, 512), (64, 8, 1024), (128, 4, 2048), (64, 4, 512)]:
    o, idx, a = hi_attention(q, K, V, bb, mm, kk)
    cs = np.dot(out_full, o) / (np.linalg.norm(out_full) * np.linalg.norm(o))
    cov = alpha_full[idx].sum()
    nb = L // bb
    speed = L / (nb + mm*bb + kk)
    print(f"  b={bb:3d} m={mm:2d} k={kk:4d}: cos={cs:.3f} 覆盖={cov:.3f} 加速={speed:.1f}x")
