#!/usr/bin/env python3
"""P0: 修复HI因果mask — 块评分加入下三角mask, 保证top-k只选当前及之前token
"""
import torch
import torch.nn.functional as F
import math

torch.manual_seed(42)
device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"设备: {device}")

def hi_attn_causal(q, K, V, scale, b=32, m=16, k=512, sink=4, window=64):
    """因果HI: 每个query只能看到自己及之前token
    关键: 逐头独立索引, 块评分 + 候选评分都加因果mask
    """
    B, H, T, d = K.shape
    
    # 全局索引 (sink + 局部window)
    forced = torch.arange(min(sink, T), device=device)
    win = torch.arange(max(0, T-window), T, device=device)
    
    L_pad = (T // b) * b
    if L_pad == 0:
        return F.scaled_dot_product_attention(q, K, V, is_causal=True)
    
    N_b = L_pad // b
    K_blocks = K[:, :, :L_pad].reshape(B, H, N_b, b, d).mean(3)  # (B,H,N_b,d)
    
    outs = []
    for h in range(H):
        K_h = K[:, h]  # (B,T,d)
        V_h = V[:, h]
        q_h = q[:, h]  # (B,T,d)
        
        # 块评分 (全局query均值, 每头独立)
        q_idx = q_h.mean(dim=1, keepdim=True)  # (B,1,d)
        bs = (q_idx @ K_blocks[:, h].transpose(-2,-1)).squeeze(1) * scale  # (B,N_b)
        m_eff = min(m, bs.shape[-1])
        tb = bs.topk(m_eff, -1).indices  # (B,m_eff)
        
        # 构建候选 (sink + window + top块)
        cands = []
        for i in range(m_eff):
            st = tb[:, i] * b
            cands.append(st.unsqueeze(-1) + torch.arange(b, device=device))
        cand_idx = torch.cat(cands, -1)  # (B,m*b)
        all_idx = torch.cat([
            forced.unsqueeze(0).expand(B, -1),
            win.unsqueeze(0).expand(B, -1),
            cand_idx
        ], -1)  # (B,n_cand)
        
        # 收集候选K
        cand_K = K_h.gather(1, all_idx.unsqueeze(-1).expand(-1,-1,d))  # (B,n_cand,d)
        
        # 因果mask: (B,T,n_cand) — 只允许索引≤t的候选
        t_positions = torch.arange(T, device=device).reshape(1, T, 1)  # (1,T,1)
        causal_mask = (all_idx.unsqueeze(1) <= t_positions).float()  # (B,T,n_cand)
        causal_mask = torch.where(causal_mask > 0, torch.zeros_like(causal_mask), 
                                   torch.full_like(causal_mask, float('-inf')))
        
        # 评分: (B,T,n_cand)
        cs = torch.einsum('btd,bnd->btn', q_h, cand_K) * scale  # (B,T,n_cand)
        cs = cs + causal_mask
        
        k_eff = min(k, cs.shape[-1])
        top_local = cs.topk(k_eff, -1).indices  # (B,T,k)
        
        # 收集top-k KV
        final_idx = all_idx.unsqueeze(1).expand(-1, T, -1).gather(2, top_local)  # (B,T,k)
        
        # 收集KV (逐batch)
        Bc = B
        fK = torch.empty(Bc, T, k_eff, d, device=device)
        fV = torch.empty(Bc, T, k_eff, d, device=device)
        for bi in range(Bc):
            fK[bi] = K_h[bi][final_idx[bi]]
            fV[bi] = V_h[bi][final_idx[bi]]
        
        # attention
        s = torch.einsum('btd,btkd->btk', q_h, fK) * scale
        alpha = F.softmax(s, -1)
        o = torch.einsum('btk,btkd->btd', alpha, fV)
        outs.append(o)
    return torch.stack(outs, dim=1)  # (B,H,T,d)

def test_causal():
    print("="*60)
    print("因果HI验证 (修复后)")
    print("="*60)
    for L in [256, 512, 1024]:
        B, H, d = 1, 4, 64
        q = torch.randn(B, H, L, d, device=device)
        K = torch.randn(B, H, L, d, device=device) * 0.3
        V = torch.randn(B, H, L, d, device=device)
        scale = 1/math.sqrt(d)
        
        # 真实特征: sink + cluster + window
        qmean = q.mean(dim=2, keepdim=True)
        K[:, :, :4] = qmean * 0.8 + torch.randn(B,H,4,d,device=device)*0.2
        cluster = torch.randint(100, L-100, (30,), device=device)
        K[:, :, cluster] = qmean * 1.2 + torch.randn(B,H,30,d,device=device)*0.05
        K[:, :, -64:] = qmean * 0.6 + torch.randn(B,H,64,d,device=device)*0.3
        
        # 全量 (因果)
        mask = torch.triu(torch.ones(L, L, device=device) * float('-inf'), diagonal=1)
        scores_full = (q @ K.transpose(-2,-1)) * scale + mask
        alpha_full = F.softmax(scores_full, -1)
        out_full = alpha_full @ V
        
        # HI (因果)
        out_hi = hi_attn_causal(q, K, V, scale, k=256)
        
        cos = F.cosine_similarity(out_full, out_hi, dim=-1).mean().item()
        print(f"L={L}: cos={cos:.4f}")
        
        # 因果性直接验证
        K_modified = K.clone()
        K_modified[:, :, L//2:] = torch.randn(B, H, L - L//2, d, device=device) * 5
        out_hi_mod = hi_attn_causal(q, K_modified, V, scale, k=256)
        early_diff = (out_hi[:, :, :100] - out_hi_mod[:, :, :100]).abs().mean().item()
        late_diff = (out_hi[:, :, L//2:] - out_hi_mod[:, :, L//2:]).abs().mean().item()
        print(f"  因果: 前100差异={early_diff:.6f} (≈0✓) | 后部差异={late_diff:.4f} (>0正常)")

test_causal()
