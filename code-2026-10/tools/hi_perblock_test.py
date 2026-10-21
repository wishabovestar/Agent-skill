#!/usr/bin/env python3
"""候选1: per-block索引 (每个query块独立HI索引) vs 全局共享索引 精度对比
真实LSA用per-block索引: 相邻query注意力相似 → 每128个query独立选top-k
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

def hi_attn_global(q, K, V, b=32, m=16, k=1024, sink=4, window=64):
    """全局共享索引 (上一版)"""
    B, Hkv, L, d = K.shape
    Hq, T = q.shape[1], q.shape[2]
    g = Hq // Hkv
    forced = torch.arange(sink, device=device)
    win = torch.arange(max(0, L-window), L, device=device)
    q_idx = q.mean(dim=(1,2), keepdim=True)
    q_idx_h = q_idx.expand(B, Hkv, 1, d)
    L_pad = (L // b) * b
    K_blocks = K[:, :, :L_pad].reshape(B, Hkv, L_pad//b, b, d).mean(3)
    bs = (q_idx_h @ K_blocks.transpose(-2, -1)).squeeze(-2) * scale
    tb = bs.topk(m, -1).indices
    all_idx_list = []
    for h in range(Hkv):
        cands = []
        for i in range(m):
            st = tb[:, h, i] * b
            cands.append(st.unsqueeze(-1) + torch.arange(b, device=device))
        cand_idx = torch.cat(cands, -1)
        all_idx = torch.cat([forced.unsqueeze(0).expand(B, -1), win.unsqueeze(0).expand(B, -1), cand_idx], -1)
        all_idx_list.append(all_idx)
    outs = []
    for h in range(Hkv):
        all_idx = all_idx_list[h]
        K_h3 = K[:, h]
        cand_K = K_h3.gather(1, all_idx.unsqueeze(-1).expand(-1, -1, d))
        cs = (q_idx.view(B, -1) @ cand_K.transpose(1, 2)).squeeze(1) * scale
        k_eff = min(k, cs.shape[-1])
        top_local = cs.topk(k_eff, -1).indices
        final_idx = all_idx.gather(1, top_local)
        fK = K[:, h].gather(1, final_idx.unsqueeze(-1).expand(-1, -1, d))
        fV = V[:, h].gather(1, final_idx.unsqueeze(-1).expand(-1, -1, d))
        q_g = q[:, h*g:(h+1)*g]
        s = (q_g @ fK.transpose(-2, -1)) * scale
        o = F.softmax(s, -1) @ fV
        outs.append(o)
    return torch.cat(outs, dim=1)

def hi_attn_perblock(q, K, V, b=32, m=16, k=1024, sink=4, window=64, qb=128):
    """per-block索引: 每qb个query独立索引 (真实LSA方式)"""
    B, Hkv, L, d = K.shape
    Hq, T = q.shape[1], q.shape[2]
    g = Hq // Hkv
    forced = torch.arange(sink, device=device)
    win = torch.arange(max(0, L-window), L, device=device)
    L_pad = (L // b) * b
    K_blocks = K[:, :, :L_pad].reshape(B, Hkv, L_pad//b, b, d).mean(3)  # (B,Hkv,N_b,d)
    
    # 将T个query分成块, 每块用块内均值做索引
    n_qb = T // qb
    outs = []
    for qi in range(n_qb):
        q_slice = q[:, :, qi*qb:(qi+1)*qb]  # (B,Hq,qb,d)
        q_idx = q_slice.mean(dim=(1,2), keepdim=True)  # (B,1,1,d)
        q_idx_h = q_idx.expand(B, Hkv, 1, d)
        bs = (q_idx_h @ K_blocks.transpose(-2, -1)).squeeze(-2) * scale  # (B,Hkv,N_b)
        tb = bs.topk(m, -1).indices
        
        all_idx_list = []
        for h in range(Hkv):
            cands = []
            for i in range(m):
                st = tb[:, h, i] * b
                cands.append(st.unsqueeze(-1) + torch.arange(b, device=device))
            cand_idx = torch.cat(cands, -1)
            all_idx = torch.cat([forced.unsqueeze(0).expand(B, -1), win.unsqueeze(0).expand(B, -1), cand_idx], -1)
            all_idx_list.append(all_idx)
        
        for h in range(Hkv):
            all_idx = all_idx_list[h]
            K_h3 = K[:, h]
            cand_K = K_h3.gather(1, all_idx.unsqueeze(-1).expand(-1, -1, d))
            cs = (q_idx.view(B, -1) @ cand_K.transpose(1, 2)).squeeze(1) * scale
            k_eff = min(k, cs.shape[-1])
            top_local = cs.topk(k_eff, -1).indices
            final_idx = all_idx.gather(1, top_local)
            fK = K[:, h].gather(1, final_idx.unsqueeze(-1).expand(-1, -1, d))
            fV = V[:, h].gather(1, final_idx.unsqueeze(-1).expand(-1, -1, d))
            q_g = q_slice[:, h*g:(h+1)*g]
            s = (q_g @ fK.transpose(-2, -1)) * scale
            o = F.softmax(s, -1) @ fV
            if h == 0:
                o_cat = o
            else:
                o_cat = torch.cat([o_cat, o], dim=1)
        outs.append(o_cat)
    return torch.cat(outs, dim=2)

def gen_realistic(L, Hq, Hkv, d, n_clusters=8):
    """生成有语义结构的真实特征数据: 每128 token块有不同主题"""
    B = 1
    q = torch.randn(B, Hq, L, d, device=device) * 0.5
    K = torch.randn(B, Hkv, L, d, device=device) * 0.3
    V = torch.randn(B, Hkv, L, d, device=device)
    # 每个256-token块: 不同主题 → 相邻query关注同一块
    for bi in range(L // 256):
        theme = torch.randn(Hkv, 1, d, device=device)
        start = bi * 256
        # 块内query关注本块theme
        q[:, :, start:start+256] = theme.mean(0, keepdim=True).expand(Hq, 256, d) * 0.8 + torch.randn(B, Hq, 256, d, device=device) * 0.3
        # 块内key
        K[:, :, start:start+256] = theme.expand(Hkv, 256, d) * 1.2 + torch.randn(B, Hkv, 256, d, device=device) * 0.05
    return q, K, V

print("="*70)
print("候选1: per-block索引 vs 全局共享索引 精度对比")
print("="*70)

for L in [8192, 16384]:
    B, Hq, Hkv, d = 1, 28, 4, 128
    q, K, V = gen_realistic(L, Hq, Hkv, d)
    
    outA = full_attn_sdpa(q, K, V)
    outG = hi_attn_global(q, K, V)
    outP = hi_attn_perblock(q, K, V)
    
    cosG = F.cosine_similarity(outA, outG, dim=-1).mean().item()
    cosP = F.cosine_similarity(outA, outP, dim=-1).mean().item()
    
    print(f"\nL={L}: 全局共享 cos={cosG:.4f} | per-block cos={cosP:.4f} | 提升 {cosP-cosG:+.4f}")
    
    # 速度
    def measure(fn, *args, repeat=3):
        for _ in range(1): fn(*args)
        torch.cuda.synchronize()
        t0 = time.time()
        for _ in range(repeat): fn(*args)
        torch.cuda.synchronize()
        return (time.time()-t0)/repeat
    
    tG = measure(hi_attn_global, q, K, V)
    tP = measure(hi_attn_perblock, q, K, V)
    tA = measure(full_attn_sdpa, q, K, V)
    print(f"  速度: 全量{tA*1000:.0f}ms | 全局{tG*1000:.0f}ms | per-block{tP*1000:.0f}ms")
