# -*- coding: utf-8 -*-
"""
TurboVec 本地模型优化验证 — 量化向量索引
==========================================
目标: 验证 TurboVec(TurboQuant) 能否高效压缩向量(如 Hermes 记忆 embeddings)
指标: 现量内存占用降低 + 召回精度
"""
import sys, io, time, numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

print("="*66)
print("TurboVec 本地优化验证 (量化向量索引)")
print("="*66)

try:
    import turbovec
    print(f"✅ turbovec 模块加载成功")
    print(f"  目录: {turbovec.__file__}")
except ImportError as e:
    print(f"❌ turbovec 导入失败: {e}")
    sys.exit(1)

# ── 1. 生成模拟向量数据集 (带聚类结构, 更接近真实记忆 embeddings) ──
DIM = 128      # embedding维度
N = 10000      # 文档数
N_CENTROIDS = 50  # 50个语义簇
rng = np.random.default_rng(42)
# 生成簇中心 + 绕中心散布 (有语义结构)
centroids = rng.standard_normal((N_CENTROIDS, DIM)) * 3
assign = rng.integers(0, N_CENTROIDS, N)
vecs = centroids[assign] + rng.standard_normal((N, DIM)) * 0.3
vecs = vecs / np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-6)
print(f"数据: {N} 文档 × {DIM}维 ({N_CENTROIDS}簇) float32 = {N*DIM*4/1e6:.1f} MB")

# ── 2. 建索引 (float32 vs turbo量化) ──
print("\n【1. 索引构建】")
vecs = np.ascontiguousarray(vecs, dtype=np.float32)  # 确保 float32 + C连续
t0=time.time()
idx = turbovec.TurboQuantIndex(DIM)
idx.add(vecs)
idx.prepare()  # TurboQuant 需要 prepare
t_float = time.time()-t0
print(f"  TurboQuant索引+prepare: {t_float:.2f}s")
print(f"  bit_width: {idx.bit_width}")

# ── 3. 检索正确性测试 ──
print("\n【2. 检索测试】(top5 最近邻)")
query = np.ascontiguousarray(vecs[0:1], dtype=np.float32)
t0=time.time()
res = idx.search(query, k=5)
t_q = time.time()-t0
print(f"  查询耗时: {t_q*1000:.2f}ms (5近邻)")
print(f"  返回类型: {type(res)} 形状: {getattr(res,'shape',res)}")
print(f"  返回: {res}")

# ── 4. 内存对比 (模拟 float32 vs 压缩估计) ──
print("\n【3. 内存压缩评估】")
mb_f = N*DIM*4/1e6
# TurboQuant 通常是 8-bit (1字节) → ~4× 压缩 (float32→int8)
mb_q = N*DIM*1/1e6
print(f"  float32: {mb_f:.1f} MB")
print(f"  量化int8(估): {mb_q:.1f} MB")
print(f"  压缩比: {mb_f/mb_q:.1f}×")

# ── 5. precision@k (量化 vs float32暴力, 均值重叠) ──
print("\n【4. 检索精度 (量化 vs float32暴力 最近邻)】")
correct = 0
total = 0
sample = 100
qq = np.ascontiguousarray(vecs[rng.integers(0, N, sample)], dtype=np.float32)
scores, ids = idx.search(qq, k=5)
# 暴力: 对每个query计算float32 top5
for i in range(sample):
    qv = qq[i]
    sims = vecs @ qv   # 点积 (单位向量)
    brute = set(np.argsort(-sims)[:5])
    qset = set(ids[i].tolist())
    correct += len(brute & qset)
    total += 5
avg = correct/total
print(f"  平均 top5 重叠率: {avg*100:.2f}%")
self_hit = sum(1 for i in range(sample) if int(np.argmax(vecs @ qq[i])) in set(ids[i].tolist()))
print(f"  query-argmax(自身)在top5: {self_hit}/{sample} ({self_hit/sample*100:.1f}%)")
print(f"  → {'✅ 检索可用' if self_hit/sample > 0.5 else '⚠️ 需排查'}")

mem_compressed = N*DIM*(idx.bit_width/8)/1e6
print(f"\n  float32 {mb_f:.1f}MB → {idx.bit_width}bit {mem_compressed:.2f}MB (压缩 {32//idx.bit_width}×)")

import json
json.dump({"dim":DIM,"n":N,"bit_width":idx.bit_width,
           "compression":round(32/idx.bit_width,1),
           "top5_overlap":round(avg*100,1),"query_ms":round(t_q*1000,2),
           "mem_mb":round(mem_compressed,2)}, 
          open("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/turbovec_verify.json","w"), ensure_ascii=False)
print(f"\n存档: knowledge_base/audit/turbovec_verify.json")
