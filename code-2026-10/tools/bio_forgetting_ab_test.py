#!/usr/bin/env python3
"""生物启发优化 A/B测试 v3 — 遗忘曲线注入块评分(真正正交)
核心: 记忆巩固机制(海马体) — 老记忆需要更强信号才被回忆
实现: 块评分时, 老块的评分被时间权重压制(需更高原始分才能入选)
对比:
  A = LSA基线 (无遗忘)
  B = LSA + 幂律遗忘 (老块评分 × 1/(1+t)^α)
  C = LSA + 指数遗忘 (老块评分 × 0.5^(t/τ))
  D = LSA + 间隔重复 (新块+已被强化的块优先)
"""
import torch
import torch.nn.functional as F
import math

torch.manual_seed(42)
device = 'cuda'
scale = 1 / math.sqrt(128)

def gen_attn_concentrated(L, n_clusters=10, cluster_size=24):
    K = torch.randn(1, L, 128, device=device) * 0.4
    for i in range(n_clusters):
        c = torch.randint(L // 4, L, (1,)).item()
        K[0, c:c+cluster_size] *= 3.2
    K[0, -64:] *= 1.8
    K[0, :4] *= 2.5
    return K

def lsa_select_forgetting(K, q, L, k=1024, b=32, m=16, sink=4, window=64, mode='none'):
    B, Ld, d = K.shape
    n_b = L // b
    q_mean = q.mean(dim=1, keepdim=True)
    K_blocks = K.view(B, n_b, b, d)
    block_centers = K_blocks.mean(dim=2)
    bs = (q_mean @ block_centers.transpose(-2, -1)).squeeze(1) * scale  # (B,n_b)
    
    # 遗忘曲线: 在块评分上乘时间权重 (老块评分被压制)
    block_idx = torch.arange(n_b, device=device).float()
    if mode == 'power':
        # 幂律遗忘: 老块降权, 但不会完全消失
        time_w = 1.0 / (1.0 + block_idx / (n_b * 0.4)) ** 0.8
        bs = bs * time_w.unsqueeze(0)
    elif mode == 'exponential':
        # 指数遗忘: 老块快速衰减
        time_w = 0.5 ** (block_idx / (n_b * 0.3))
        bs = bs * time_w.unsqueeze(0)
    elif mode == 'interleaved':
        # 间隔重复: 幂律 + 周期强化 (老块周期性恢复)
        time_w = 1.0 / (1.0 + block_idx / (n_b * 0.4)) ** 0.8
        boost = 1.0 + 0.6 * (0.5 + 0.5 * torch.sin(block_idx / 3.0))  # 周期强化
        bs = bs * time_w.unsqueeze(0) * boost.unsqueeze(0)
    
    top_b = bs.topk(min(m, n_b), -1).indices
    cands = set(range(min(sink, L)))
    cands.update(range(L - window, L))
    for i in range(min(m, n_b)):
        st = top_b[0, i].item() * b
        cands.update(range(st, min(st + b, L)))
    idx = torch.tensor(sorted(cands), device=device)
    return idx[:k]

def evaluate(L=8192, k=1024):
    K = gen_attn_concentrated(L)
    V = K
    q = K.mean(dim=1, keepdim=True)
    
    scores_full = q @ K.transpose(-2, -1) * scale
    alpha_full = F.softmax(scores_full, -1)
    o_full = alpha_full @ V
    topk_full = alpha_full[0, 0].topk(k).indices.tolist()
    
    results = {}
    for mode in ['none', 'power', 'exponential', 'interleaved']:
        idx = lsa_select_forgetting(K, q, L, k=k, mode=mode)
        K_sub = K[:, idx]
        scores_sub = q @ K_sub.transpose(-2, -1) * scale
        alpha_sub = F.softmax(scores_sub, -1)
        o_sub = alpha_sub @ K_sub
        
        cos = F.cosine_similarity(o_full[0, 0], o_sub[0, 0], dim=-1).item()
        overlap = len(set(idx.tolist()) & set(topk_full)) / k
        results[mode] = {'cos': round(cos, 4), 'overlap': round(overlap, 4)}
    return results

if __name__ == '__main__':
    print("=== 生物遗忘曲线注入块评分 A/B测试 ===")
    print("L=8192, k=1024 (sink4+window64+topk块)\n")
    r = evaluate()
    for mode, d in r.items():
        print(f"  {mode:15s} cos={d['cos']:.4f}  与全量top-k重叠={d['overlap']*100:.1f}%")
    
    print("\n=== 结论 ===")
    base = r['none']
    best_name = max(r, key=lambda k: r[k]['cos'])
    best = r[best_name]
    delta = (best['cos'] - base['cos']) * 100
    print(f"  基线: {base['cos']:.4f} | 最优: {best_name} ({best['cos']:.4f})")
    print(f"  cos变化: {delta:+.2f}%")
    if delta > 0.5:
        print(f"  ✅ {best_name} 显著优于基线 — 生物遗忘曲线可提升LSA")
    elif delta < -0.5:
        print(f"  ⚠️ {best_name} 差于基线 — 遗忘曲线不适合当前配置")
    else:
        print(f"  ➖ 无明显差异 — 遗忘曲线与LSA正交(不损害也不提升)")
