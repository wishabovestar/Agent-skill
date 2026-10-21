#!/usr/bin/env python3
"""A/B测试 v3: SDPA-Flash (A) vs LSA-HI稀疏 (B)
- A用F.scaled_dot_product_attention (flash内核, 分块不OOM)
- B用共享索引HI (仅索引计算+稀疏attention)
- 核心指标: 内存上限 + 精度(cos) + 理论计算加速
"""
import torch
import torch.nn.functional as F
import time, math, json, os

torch.manual_seed(42)
device = 'cuda'
print(f"设备: {torch.cuda.get_device_name(0)} | {torch.cuda.get_device_properties(0).total_memory/1e9:.1f}GB")
scale = 1.0 / math.sqrt(128)

# ============ A: SDPA flash attention (工业基线) ============
def full_attn_sdpa(q, K, V):
    """q:(B,Hq,T,d) K,V:(B,Hkv,L,d) — GQA手动扩展"""
    B, Hkv, L, d = K.shape
    Hq = q.shape[1]
    g = Hq // Hkv
    K_e = K.repeat_interleave(g, dim=1)  # (B,Hq,L,d)
    V_e = V.repeat_interleave(g, dim=1)
    return F.scaled_dot_product_attention(q, K_e, V_e, is_causal=False)

# ============ B: HI稀疏attention (共享索引) ============
def hi_attn(q, K, V, b=32, m=16, k=1024, sink=4, window=64):
    B, Hkv, L, d = K.shape
    Hq, T = q.shape[1], q.shape[2]
    g = Hq // Hkv
    
    forced = torch.arange(sink, device=device)
    win = torch.arange(max(0, L-window), L, device=device)
    
    # 全局共享索引 (基于所有query均值)
    q_idx = q.mean(dim=(1,2), keepdim=True)  # (B,1,1,d)
    q_idx_h = q_idx.expand(B, Hkv, 1, d)  # (B,Hkv,1,d)
    L_pad = (L // b) * b
    K_blocks = K[:, :, :L_pad].reshape(B, Hkv, L_pad//b, b, d).mean(3)  # (B,Hkv,N_b,d)
    bs = (q_idx_h @ K_blocks.transpose(-2, -1)).squeeze(-2) * scale  # (B,Hkv,N_b)
    tb = bs.topk(m, -1).indices  # (B,Hkv,m)
    
    # 候选索引 (每KV头)
    all_idx_list = []
    for h in range(Hkv):
        cands = []
        for i in range(m):
            st = tb[:, h, i] * b  # (B,)
            cands.append(st.unsqueeze(-1) + torch.arange(b, device=device))
        cand_idx = torch.cat(cands, -1)  # (B,m*b)
        all_idx = torch.cat([
            forced.unsqueeze(0).expand(B, -1),
            win.unsqueeze(0).expand(B, -1),
            cand_idx
        ], -1)  # (B,n_cand)
        all_idx_list.append(all_idx)
    
    # 细评分 → top-k (每KV头)
    outs = []
    for h in range(Hkv):
        all_idx = all_idx_list[h]  # (B,n_cand)
        # 收集候选K
        K_h3 = K[:, h]  # (B,L,d)
        cand_K = K_h3.gather(1, all_idx.unsqueeze(-1).expand(-1, -1, d))  # (B,n_cand,d)
        cs = (q_idx.view(B, -1) @ cand_K.transpose(1, 2)).squeeze(1) * scale  # (B,n_cand)
        k_eff = min(k, cs.shape[-1])
        top_local = cs.topk(k_eff, -1).indices  # (B,k)
        final_idx = all_idx.gather(1, top_local)  # (B,k)
        
        # 收集最终KV (gather方式)
        Bb = K.shape[0]
        fK = K[:, h].gather(1, final_idx.unsqueeze(-1).expand(-1, -1, d))  # (B,k,d)
        fV = V[:, h].gather(1, final_idx.unsqueeze(-1).expand(-1, -1, d))
        # 广播到T个query
        q_g = q[:, h*g:(h+1)*g]  # (B,g,T,d)
        s = (q_g @ fK.transpose(-2, -1)) * scale  # (B,g,T,k)
        o = F.softmax(s, -1) @ fV  # (B,g,T,d)
        outs.append(o)
    
    return torch.cat(outs, dim=1)

def measure(fn, *args, warmup=2, repeat=5):
    for _ in range(warmup):
        fn(*args)
    torch.cuda.synchronize()
    times = []
    for _ in range(repeat):
        t0 = time.time()
        fn(*args)
        torch.cuda.synchronize()
        times.append(time.time() - t0)
    return min(times)

print("\n" + "="*70)
print("A/B测试: prefill (L token为query) — SDPA vs HI")
print("="*70)
results = []
for L in [8192, 16384, 32768]:
    B, Hq, Hkv, d = 1, 28, 4, 128
    q = torch.randn(B, Hq, L, d, device=device) * 0.5
    K = torch.randn(B, Hkv, L, d, device=device) * 0.3
    V = torch.randn(B, Hkv, L, d, device=device)
    
    # 精度测试 (真实特征: sink+cluster+window)
    Kt = K.clone()
    qt = torch.randn(B, Hq, L, d, device=device) * 0.5
    qmean = qt[:, :Hkv].mean(dim=(1,2), keepdim=True)
    Kt[:, :, :4] = qmean.expand(B, Hkv, 4, d) * 0.8 + torch.randn(B, Hkv, 4, d, device=device) * 0.2
    cluster = torch.randint(100, L-100, (30,), device=device)
    Kt[:, :, cluster] = qmean.expand(B, Hkv, 30, d) * 1.2 + torch.randn(B, Hkv, 30, d, device=device) * 0.05
    Kt[:, :, -64:] = qmean.expand(B, Hkv, 64, d) * 0.6 + torch.randn(B, Hkv, 64, d, device=device) * 0.3
    
    # A: SDPA
    torch.cuda.reset_peak_memory_stats()
    try:
        tA = measure(full_attn_sdpa, qt, Kt, V, warmup=1, repeat=2)
        memA = torch.cuda.max_memory_allocated()/1e9
        statusA = f"{tA*1000:7.0f}ms"
    except Exception as e:
        statusA = f"OOM({str(e)[:20]})"
        memA = torch.cuda.max_memory_allocated()/1e9
    torch.cuda.empty_cache()
    
    # B: HI
    torch.cuda.reset_peak_memory_stats()
    try:
        tB = measure(hi_attn, qt, Kt, V, warmup=1, repeat=2)
        memB = torch.cuda.max_memory_allocated()/1e9
        statusB = f"{tB*1000:7.0f}ms"
    except Exception as e:
        import traceback
        traceback.print_exc()
        statusB = f"OOM({str(e)[:40]})"
        memB = torch.cuda.max_memory_allocated()/1e9
    torch.cuda.empty_cache()
    
    # cos精度
    try:
        outA = full_attn_sdpa(qt, Kt, V)
        outB = hi_attn(qt, Kt, V)
        cos = F.cosine_similarity(outA, outB, dim=-1).mean().item()
    except:
        cos = float('nan')
    
    print(f"L={L:6d}: A {statusA} (峰值{memA:.1f}GB) | B {statusB} (峰值{memB:.1f}GB) | cos={cos:.3f}")
    results.append({'L': L, 'A_time': statusA, 'A_mem': memA, 'B_time': statusB, 'B_mem': memB, 'cos': cos})

os.makedirs(r'D:/hermes/data/results', exist_ok=True)
with open(r'D:/hermes/data/results/ab_lsa_hi_test.json', 'w') as f:
    json.dump(results, f, indent=2)
print(f"\n✅ 结果已存: results/ab_lsa_hi_test.json")
