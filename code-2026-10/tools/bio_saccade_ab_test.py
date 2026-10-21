#!/usr/bin/env python3
"""生物启发A/B测试v4 — 视觉扫视机制: 动态k选择
生物依据: 人类视觉=中央凹(高分辨率,聚焦)+周边(低分辨率,上下文)
  扫视(saccade): 眼睛快速移动, 每次聚焦不同区域
映射: LSA的topk块选择 → 两次扫视(两个焦点区)替代单次全搜索
对比:
  A = LSA单焦点 (k=1024, 1次topk)
  B = LSA双焦点扫视 (k1=512近端 + k2=512远端)
  C = LSA动态k (按注意力集中度C自适应: C高→小k, C低→大k)
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

def lsa_dual_saccade(K, q, L, k=1024, b=32, sink=4, window=64):
    """双焦点扫视: 近端焦点(最近1/4)+远端焦点(前3/4)"""
    B, Ld, d = K.shape
    k_half = k // 2
    
    # 近端焦点: 在最近1/4中选
    near_start = L * 3 // 4
    n_b_near = (L - near_start) // b
    if n_b_near < 1: n_b_near = 1
    K_near = K[:, near_start:].view(B, n_b_near, b, d)
    q_mean = q.mean(dim=1, keepdim=True)
    bs_near = (q_mean @ K_near.mean(2).transpose(-2,-1)).squeeze(1) * scale
    m_near = max(1, k_half // b)
    top_near = bs_near.topk(min(m_near, n_b_near), -1).indices
    
    # 远端焦点: 在前3/4中选
    far_end = L * 3 // 4
    n_b_far = far_end // b
    K_far = K[:, :far_end].view(B, n_b_far, b, d)
    bs_far = (q_mean @ K_far.mean(2).transpose(-2,-1)).squeeze(1) * scale
    m_far = max(1, k_half // b)
    top_far = bs_far.topk(min(m_far, n_b_far), -1).indices
    
    cands = set(range(min(sink, L)))
    cands.update(range(L - window, L))
    for i in range(min(m_near, n_b_near)):
        st = near_start + top_near[0, i].item() * b
        cands.update(range(st, min(st + b, L)))
    for i in range(min(m_far, n_b_far)):
        st = top_far[0, i].item() * b
        cands.update(range(st, min(st + b, L)))
    return torch.tensor(sorted(cands), device=device)[:k]

def attention_concentration(K, q, L, b=32):
    """注意力集中度C: top-256块覆盖的注意力比例"""
    n_b = L // b
    q_mean = q.mean(dim=1, keepdim=True)
    K_blocks = K.view(1, n_b, b, 128)
    bs = (q_mean @ K_blocks.mean(2).transpose(-2,-1)).squeeze(1) * scale
    top256 = bs.topk(min(256, n_b), -1).indices
    total = bs.sum()
    covered = bs[0, top256[0]].sum()
    return (covered / total).item()

def evaluate(L=8192):
    K = gen_attn_concentrated(L)
    V = K
    q = K.mean(dim=1, keepdim=True)
    
    o_full = F.softmax(q @ K.transpose(-2, -1) * scale, -1) @ V
    topk_full = F.softmax(q @ K.transpose(-2, -1) * scale, -1)[0, 0].topk(1024).indices.tolist()
    
    results = {}
    
    # A: 单焦点
    idx_a = lsa_select(K, q, L, k=1024)
    o_a = F.softmax(q @ K[:, idx_a].transpose(-2,-1) * scale, -1) @ K[:, idx_a]
    results['A_single_focus'] = {
        'cos': F.cosine_similarity(o_full[0,0], o_a[0,0], dim=-1).item(),
        'overlap': len(set(idx_a.tolist()) & set(topk_full)) / 1024
    }
    
    # B: 双焦点扫视
    idx_b = lsa_dual_saccade(K, q, L, k=1024)
    o_b = F.softmax(q @ K[:, idx_b].transpose(-2,-1) * scale, -1) @ K[:, idx_b]
    results['B_dual_saccade'] = {
        'cos': F.cosine_similarity(o_full[0,0], o_b[0,0], dim=-1).item(),
        'overlap': len(set(idx_b.tolist()) & set(topk_full)) / 1024
    }
    
    # C: 动态k (注意力集中度高→小k)
    C = attention_concentration(K, q, L)
    k_dyn = int(1024 * (0.5 + 0.5 * C))  # C高→k小
    idx_c = lsa_select(K, q, L, k=k_dyn)
    o_c = F.softmax(q @ K[:, idx_c].transpose(-2,-1) * scale, -1) @ K[:, idx_c]
    results['C_dynamic_k'] = {
        'cos': F.cosine_similarity(o_full[0,0], o_c[0,0], dim=-1).item(),
        'overlap': len(set(idx_c.tolist()) & set(topk_full)) / 1024,
        'k_used': k_dyn,
        'C': C
    }
    return results

if __name__ == '__main__':
    print("=== 视觉扫视机制 A/B测试 ===\n")
    r = evaluate()
    for name, d in r.items():
        print(f"  {name:18s} cos={d['cos']:.4f} 重叠={d['overlap']*100:.1f}%" + 
              (f"  k={d['k_used']} C={d['C']:.3f}" if 'k_used' in d else ''))
    
    print("\n=== 结论 ===")
    base = r['A_single_focus']
    for name, d in r.items():
        delta = (d['cos'] - base['cos']) * 100
        tag = "✅提升" if delta > 0.5 else ("➖中性" if abs(delta) <= 0.5 else "❌下降")
        print(f"  {name}: {delta:+.2f}% vs 单焦点 → {tag}")
