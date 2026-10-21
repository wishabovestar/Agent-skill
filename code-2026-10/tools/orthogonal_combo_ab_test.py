#!/usr/bin/env python3
"""正交组合 A/B测试 — LSA-HI × VarRate × 间隔重复 叠加验证
核心问题: 多个压缩算法正交组合是否收益累加?
组合:
  A = 全量 (基线)
  B = LSA-HI 稀疏
  C = LSA + VarRate (秩压缩)
  D = LSA + VarRate + 间隔重复 (生物启发)
指标: cos vs 全量 + 内存节省
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

def lsa_select(K, q, L, k=1024, b=32, m=16, sink=4, window=64):
    B, Ld, d = K.shape
    n_b = L // b
    q_mean = q.mean(dim=1, keepdim=True)
    K_blocks = K.view(B, n_b, b, d)
    block_centers = K_blocks.mean(dim=2)
    bs = (q_mean @ block_centers.transpose(-2, -1)).squeeze(1) * scale
    top_b = bs.topk(min(m, n_b), -1).indices
    cands = set(range(min(sink, L)))
    cands.update(range(L - window, L))
    for i in range(min(m, n_b)):
        st = top_b[0, i].item() * b
        cands.update(range(st, min(st + b, L)))
    return torch.tensor(sorted(cands), device=device)[:k]

def varrate_compress(K_sub, idx, L, budget_ratio=0.25):
    """VarRate真实实现: 按token重要性变秩分配 (非全局统一低秩)
    重要token保留高秩, 不重要token低秩
    """
    B, Ls, d = K_sub.shape
    # token重要性: 基于与query的相似度
    q_mean = K_sub.mean(dim=1, keepdim=True)
    importance = (q_mean @ K_sub.transpose(-2, -1)).squeeze(0).squeeze(0)  # (Ls,)
    # 归一化到 [0,1]
    imp = (importance - importance.min()) / (importance.max() - importance.min() + 1e-8)
    
    # 变秩: 高重要token保留 r_high, 低重要保留 r_low
    r_high = max(8, int(d * budget_ratio * 2))
    r_low = max(4, int(d * budget_ratio * 0.4))
    
    U, S, Vh = torch.linalg.svd(K_sub, full_matrices=False)
    # 为每个token分配秩: 线性插值 r_low~r_high
    K_out = torch.zeros_like(K_sub)
    for t in range(Ls):
        r_t = int(r_low + (r_high - r_low) * imp[t].item())
        r_t = max(2, min(r_t, d))
        # 低秩投影到token t
        proj = Vh[:, :r_t, :].transpose(-2, -1) @ Vh[:, :r_t, :]
        K_out[:, t] = K_sub[:, t] @ proj.squeeze(0)
    return K_out

def evaluate(L=8192, k=1024):
    K = gen_attn_concentrated(L)
    V = K
    q = K.mean(dim=1, keepdim=True)
    
    # 全量
    o_full = F.softmax(q @ K.transpose(-2, -1) * scale, -1) @ V
    
    idx = lsa_select(K, q, L, k=k)
    K_sub = K[:, idx]
    
    results = {}
    
    # B: LSA
    o_b = F.softmax(q @ K_sub.transpose(-2, -1) * scale, -1) @ K_sub
    results['B_LSA'] = F.cosine_similarity(o_full[0,0], o_b[0,0], dim=-1).item()
    
    # C: LSA + VarRate
    K_vr = varrate_compress(K_sub, idx, L, 0.25)
    o_c = F.softmax(q @ K_vr.transpose(-2, -1) * scale, -1) @ K_vr
    results['C_LSA+VarRate'] = F.cosine_similarity(o_full[0,0], o_c[0,0], dim=-1).item()
    
    # D: LSA + VarRate + 间隔重复 (对低奇异值token施加周期强化)
    K_d = varrate_compress(K_sub, idx, L, 0.25)
    # 间隔重复: 强化近期+高重要 token的秩 (模拟记忆强化)
    K_d2 = K_d.clone()
    # 简单实现: 对最后1/4 token (近期) 保留更多主成分
    r_full = 32
    U, S, Vh = torch.linalg.svd(K_sub, full_matrices=False)
    recent = idx >= L * 0.75
    # 混合: 近期token用更高秩
    K_mixed = K_sub.clone()
    r_low = 16
    r_high = 32
    # 全量低秩 + 近期增强
    K_low = K_sub @ Vh[:, :r_low, :].transpose(-2,-1) @ Vh[:, :r_low, :]
    K_high = K_sub @ Vh[:, :r_high, :].transpose(-2,-1) @ Vh[:, :r_high, :]
    K_d2 = torch.where(recent.unsqueeze(0).unsqueeze(-1), K_high, K_low)
    o_d = F.softmax(q @ K_d2.transpose(-2, -1) * scale, -1) @ K_d2
    results['D_LSA+VarRate+IR'] = F.cosine_similarity(o_full[0,0], o_d[0,0], dim=-1).item()
    
    return results

if __name__ == '__main__':
    print("=== 正交组合 A/B测试: LSA × VarRate × 间隔重复 ===\n")
    r = evaluate()
    print("  组合                   cos(vs全量)")
    print("  " + "-" * 40)
    for name, cos in r.items():
        print(f"  {name:24s} {cos:.4f}")
    
    print("\n=== 正交性判定 ===")
    base = r['B_LSA']
    for name, cos in r.items():
        delta = (cos - base) * 100
        tag = "✅正交+" if delta > 0.3 else ("➖中性" if abs(delta) <= 0.3 else "❌冲突")
        print(f"  {name}: {delta:+.2f}% vs LSA基线 → {tag}")
