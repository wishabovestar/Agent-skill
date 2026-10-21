#!/usr/bin/env python3
"""LSA HI稀疏attention — PyTorch CUDA GPU原型 (P2-C方案)
验证: 在RTX 5070上对比全量attention vs HI稀疏attention的速度/精度
"""
import torch
import torch.nn.functional as F
import time
import math

torch.manual_seed(42)
device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"设备: {device} | {torch.cuda.get_device_name(0) if device=='cuda' else 'CPU'}")

def full_attention(q, K, V, scale):
    """全量attention (ground truth)"""
    scores = (q @ K.transpose(-2, -1)) * scale
    alpha = F.softmax(scores, dim=-1)
    return alpha @ V, alpha

def hi_sparse_attention(q, K, V, scale, b=32, m=16, k=512, sink=4, window=64):
    """HI分层索引稀疏attention (GPU向量化)"""
    B, H, L, d = K.shape
    # 强制保留 sink + window
    forced = torch.arange(sink, device=device)
    window_idx = torch.arange(L-window, L, device=device)
    
    # 粗阶段: 块聚合
    L_pad = (L // b) * b
    K_blocks = K[:, :, :L_pad].reshape(B, H, L_pad//b, b, d).mean(dim=3)  # (B,H,N_b,d)
    block_scores = (q @ K_blocks.transpose(-2, -1)).squeeze(-2) * scale  # (B,H,N_b)
    top_blocks = block_scores.topk(m, dim=-1).indices  # (B,H,m)
    
    # 细阶段: 选块内所有token评分
    candidates = []
    for bi in range(m):
        start = top_blocks[..., bi] * b  # (B,H)
        idx = start.unsqueeze(-1) + torch.arange(b, device=device)  # (B,H,b)
        candidates.append(idx)
    cand_idx = torch.cat(candidates, dim=-1)  # (B,H,m*b)
    
    # 合并排序取top-k (逐batch-head)
    Bc, Hc = q.shape[:2]
    forced3d = forced.unsqueeze(0).unsqueeze(0).expand(Bc, Hc, -1)  # (B,H,sink)
    window3d = window_idx.unsqueeze(0).unsqueeze(0).expand(Bc, Hc, -1)  # (B,H,window)
    all_idx = torch.cat([forced3d, window3d, cand_idx], dim=-1)  # (B,H,sink+window+m*b)
    
    # 收集候选KV
    cand_K = torch.gather(K.expand(Bc, Hc, L, d), 2, all_idx.unsqueeze(-1).expand(-1, -1, -1, d))
    cand_V = torch.gather(V.expand(Bc, Hc, L, d), 2, all_idx.unsqueeze(-1).expand(-1, -1, -1, d))
    
    # 候选评分 → top-k
    cand_scores = (q @ cand_K.transpose(-2, -1)).squeeze(-2) * scale  # (B,H,n_cand)
    top_k_local = cand_scores.topk(k, dim=-1).indices  # (B,H,k)
    
    # 收集top-k
    final_idx = torch.gather(all_idx, 2, top_k_local)
    final_K = torch.gather(K.expand(Bc, Hc, L, d), 2, final_idx.unsqueeze(-1).expand(-1, -1, -1, d))
    final_V = torch.gather(V.expand(Bc, Hc, L, d), 2, final_idx.unsqueeze(-1).expand(-1, -1, -1, d))
    
    # 稀疏attention
    scores = (q @ final_K.transpose(-2, -1)).squeeze(-2) * scale
    alpha = F.softmax(scores, dim=-1)
    out = (alpha.unsqueeze(-2) @ final_V).squeeze(-2)
    return out, final_idx

def measure(fn, *args, repeat=5):
    """测速"""
    # warmup
    fn(*args)
    torch.cuda.synchronize()
    times = []
    for _ in range(repeat):
        t0 = time.time()
        fn(*args)
        torch.cuda.synchronize()
        times.append(time.time() - t0)
    return min(times)

# ============ 实验配置 ============
print("\n" + "="*60)
print("实验1: 精度验证 (L=4096)")
print("="*60)
L, d = 4096, 64
B, H = 1, 1
scale = 1.0 / math.sqrt(d)

# 真实LLM特征数据: sink + 语义簇 + 窗口
K = torch.randn(B, H, L, d, device=device) * 0.3
q = torch.randn(B, H, 1, d, device=device)
K[:, :, :4] = q * 0.8 + torch.randn(B, H, 4, d, device=device) * 0.2
cluster = torch.randint(100, L-100, (30,), device=device)
K[:, :, cluster] = q * 1.2 + torch.randn(B, H, 30, d, device=device) * 0.05
K[:, :, -64:] = q * 0.6 + torch.randn(B, H, 64, d, device=device) * 0.3
V = torch.randn(B, H, L, d, device=device)

out_full, alpha_full = full_attention(q, K, V, scale)
out_hi, idx_hi = hi_sparse_attention(q, K, V, scale)

cos = F.cosine_similarity(out_full, out_hi, dim=-1).item()
covered = alpha_full[..., idx_hi[0,0]].sum().item()
print(f"cos相似度: {cos:.4f}")
print(f"注意力覆盖: {covered:.3f} ({covered*100:.1f}%)")
print(f"HI选中token数: {idx_hi.shape[-1]}")

# ============ 实验2: 速度对比 (GPU) ============
print("\n" + "="*60)
print("实验2: GPU速度对比 (RTX 5070)")
print("="*60)
for L in [4096, 8192, 16384]:
    K2 = torch.randn(1, 1, L, d, device=device) * 0.3
    q2 = torch.randn(1, 1, 1, d, device=device)
    V2 = torch.randn(1, 1, L, d, device=device)
    
    t_full = measure(full_attention, q2, K2, V2, scale)
    t_hi = measure(hi_sparse_attention, q2, K2, V2, scale)
    
    print(f"\nL={L}: 全量 {t_full*1000:.2f}ms | HI {t_hi*1000:.2f}ms | 加速 {t_full/t_hi:.1f}x")
    # 理论计算量
    full_flops = L * d * 2
    hi_flops = (L//32 + 16*32 + 512) * d * 2
    print(f"  理论计算量比: {full_flops/hi_flops:.1f}x (实现开销会稀释)")

print("\n" + "="*60)
print("实验3: 64K上下文外推 (12GB目标)")
print("="*60)
L = 65536
K3 = torch.randn(1, 1, L, d, device=device) * 0.3
q3 = torch.randn(1, 1, 1, d, device=device)
V3 = torch.randn(1, 1, L, d, device=device)

t_full = measure(full_attention, q3, K3, V3, scale)
t_hi = measure(hi_sparse_attention, q3, K3, V3, scale)
print(f"L=64K: 全量 {t_full*1000:.0f}ms | HI {t_hi*1000:.0f}ms | 加速 {t_full/t_hi:.1f}x")
print(f"内存: 全量score {(L**2)*4/1e9:.1f}GB vs HI稀疏 {(512*64*4)/1e6:.2f}MB")
