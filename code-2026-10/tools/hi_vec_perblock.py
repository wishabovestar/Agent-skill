#!/usr/bin/env python3
"""候选1b: 向量化per-block HI — 消除Python循环, 同时获得高精度+高速
关键: 所有块并行处理 (batch dim = n_qb × Hkv)
"""
import torch
import torch.nn.functional as F
import time, math

torch.manual_seed(42)
device = 'cuda'
scale = 1.0 / math.sqrt(128)

def full_attn_sdpa(q, K, V):
    B, Hkv, L, d = K.shape
    Hq = q.shape[1]
    g = Hq // Hkv
    K_e = K.repeat_interleave(g, dim=1)
    V_e = V.repeat_interleave(g, dim=1)
    return F.scaled_dot_product_attention(q, K_e, V_e, is_causal=False)

def hi_attn_vec_perblock(q, K, V, b=32, m=16, k=1024, sink=4, window=64, qb=128):
    """向量化per-block: 所有query块同时索引"""
    B, Hkv, L, d = K.shape
    Hq, T = q.shape[1], q.shape[2]
    g = Hq // Hkv
    n_qb = T // qb
    
    # reshape query到块: (B, n_qb, Hq, qb, d)
    q_r = q.reshape(B, n_qb, Hq, qb, d)
    q_idx = q_r.mean(dim=(2,3), keepdim=True)  # (B, n_qb, 1, 1, d)
    
    # 块KV: (B, Hkv, N_b, d)
    L_pad = (L // b) * b
    K_blocks = K[:, :, :L_pad].reshape(B, Hkv, L_pad//b, b, d).mean(3)
    
    # 粗评分: (B, n_qb, Hkv, N_b)
    bs = torch.einsum('bnqd,bhNd->bnhN', q_idx.squeeze(3), K_blocks) * scale
    tb = bs.topk(m, -1).indices  # (B, n_qb, Hkv, m)
    
    # 构建候选索引: (B, n_qb, Hkv, n_cand)
    offs = torch.arange(b, device=device).reshape(1, 1, 1, b)  # (1,1,1,b)
    cand_offsets = (tb.unsqueeze(-1) * b + offs).reshape(B, n_qb, Hkv, m*b)  # (B,nqb,Hkv,m*b)
    forced = torch.arange(sink, device=device).reshape(1, 1, 1, sink).expand(B, n_qb, Hkv, -1)
    win = torch.arange(max(0, L-window), L, device=device).reshape(1, 1, 1, window).expand(B, n_qb, Hkv, -1)
    all_idx = torch.cat([forced, win, cand_offsets], -1)  # (B, n_qb, Hkv, n_cand)
    
    # 收集候选K: (B, n_qb, Hkv, n_cand, d)
    K_e = K.unsqueeze(1).expand(B, n_qb, Hkv, L, d)  # (B,nqb,Hkv,L,d)
    cand_K = torch.gather(K_e, 3, all_idx.unsqueeze(-1).expand(-1, -1, -1, -1, d))
    
    # 细评分: (B, n_qb, Hkv, n_cand)
    q_idx_h = q_idx.squeeze(3).unsqueeze(2).expand(B, n_qb, Hkv, 1, d)  # (B,nqb,Hkv,1,d)
    cs = torch.einsum('bnhqd,bnhNd->bnhN', q_idx_h, cand_K) * scale
    k_eff = min(k, cs.shape[-1])
    top_local = cs.topk(k_eff, -1).indices  # (B,nqb,Hkv,k)
    
    # 最终索引: (B,nqb,Hkv,k)
    final_idx = torch.gather(all_idx, 3, top_local)
    
    # 收集最终KV: (B,nqb,Hkv,k,d)
    fK = torch.gather(K_e, 3, final_idx.unsqueeze(-1).expand(-1, -1, -1, -1, d))
    fV = torch.gather(K_e, 3, final_idx.unsqueeze(-1).expand(-1, -1, -1, -1, d))
    fV = torch.gather(V.unsqueeze(1).expand(B, n_qb, Hkv, L, d), 3, final_idx.unsqueeze(-1).expand(-1, -1, -1, -1, d))
    
    # 扩展KV到g组: (B, n_qb, Hq, k_eff, d)
    fK_g = fK.unsqueeze(3).expand(B, n_qb, Hkv, g, k_eff, d).reshape(B, n_qb, Hq, k_eff, d)
    fV_g = fV.unsqueeze(3).expand(B, n_qb, Hkv, g, k_eff, d).reshape(B, n_qb, Hq, k_eff, d)
    
    # attention: (B, n_qb, Hq, qb, k) → out (B, n_qb, Hq, qb, d)
    s = torch.einsum('bnhqd,bnhkd->bnhqk', q_r, fK_g) * scale
    alpha = F.softmax(s, dim=-1)
    out = torch.einsum('bnhqk,bnhkd->bnhqd', alpha, fV_g)
    
    return out.reshape(B, Hq, T, d)

def gen_realistic(L, Hq, Hkv, d, theme_len=256):
    B = 1
    q = torch.randn(B, Hq, L, d, device=device) * 0.5
    K = torch.randn(B, Hkv, L, d, device=device) * 0.3
    V = torch.randn(B, Hkv, L, d, device=device)
    for bi in range(L // theme_len):
        theme = torch.randn(Hkv, 1, d, device=device)
        start = bi * theme_len
        q[:, :, start:start+theme_len] = theme.mean(0, keepdim=True).expand(Hq, theme_len, d) * 0.8 + torch.randn(B, Hq, theme_len, d, device=device) * 0.3
        K[:, :, start:start+theme_len] = theme.expand(Hkv, theme_len, d) * 1.2 + torch.randn(B, Hkv, theme_len, d, device=device) * 0.05
    return q, K, V

def measure(fn, *args, warmup=1, repeat=3):
    for _ in range(warmup): fn(*args)
    torch.cuda.synchronize()
    t0 = time.time()
    for _ in range(repeat): fn(*args)
    torch.cuda.synchronize()
    return (time.time()-t0)/repeat

print("="*70)
print("向量化per-block HI: 精度+速度综合验证")
print("="*70)
for L in [8192, 16384, 32768]:
    B, Hq, Hkv, d = 1, 28, 4, 128
    q, K, V = gen_realistic(L, Hq, Hkv, d)
    
    outA = full_attn_sdpa(q, K, V)
    outP = hi_attn_vec_perblock(q, K, V)
    cos = F.cosine_similarity(outA, outP, dim=-1).mean().item()
    
    tA = measure(full_attn_sdpa, q, K, V)
    tP = measure(hi_attn_vec_perblock, q, K, V)
    
    print(f"\nL={L:6d}: cos={cos:.4f} | 全量 {tA*1000:6.0f}ms | 向量HI {tP*1000:6.0f}ms | 加速 {tA/max(tP,1e-9):5.1f}x")
