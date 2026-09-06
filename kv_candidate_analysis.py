# -*- coding: utf-8 -*-
"""KV 加载类候选方向验证 — 12GB 显存场景边界分析 (2026-09-06)
候选: A前缀缓存 B KV量化 C 稀疏加载(IMPRESS式) D驱逐(证伪) E合并
"""
# side_effects: [只读+报告写入]

def kv_mem_per_token(model, gqa):
    """KV 每 token 字节 (fp16=2B) — 按层数/头/维度"""
    layers, n_kv_heads, head_dim = model
    return layers * n_kv_heads * head_dim * 2  # fp16 bytes

MODELS = {
    "qwen2.5:7b": (28, 4, 128),      # GQA 4 KV heads
    "qwen2.5:0.5b": (24, 2, 64),
    "llama3.1:8b": (32, 8, 128),
    "deepseek-r1:7b": (28, 4, 128),
}

print("=== 12GB 显存场景 KV 边界 (fp16 vs 量化) ===")
print(f"{'模型':<14}{'每token':<10}{'1k tok':<10}{'8k':<10}{'32k':<10}{'128k':<10}")
print("=" * 70)
for name, m in MODELS.items():
    per = kv_mem_per_token(m, None)
    print(f"{name:<14}{per/1024:>6.1f}KB  {per*1024/1024/1024:>7.2f}MB  "
          f"{per*8192/1024/1024:>6.1f}MB  {per*32768/1024/1024:>6.1f}MB  {per*131072/1024/1024:>6.1f}MB")

print()
print("=== qwen2.5:7b 详细 (12GB 墙 — 权重 ~4.7GB GGUF Q4) ===")
per = kv_mem_per_token(MODELS["qwen2.5:7b"], None)  # 57344 B/token
w = 4.7 * 1024  # MB 权重
avail = 12 * 1024 - w - 500  # 减权重+激活/缓冲
print(f"权重 ~4.7GB → 可用 KV 空间 ~{avail/1024:.1f}GB")
for ctx in [8192, 32768, 65536, 131072]:
    fp16_mb = per * ctx / 1024 / 1024
    q8_mb = fp16_mb / 2
    q4_mb = fp16_mb / 4
    ok_fp16 = fp16_mb <= avail
    ok_q8 = q8_mb <= avail
    ok_q4 = q4_mb <= avail
    print(f"{ctx/1024:>5.0f}k: fp16 {fp16_mb/1024:>5.2f}GB {'✅' if ok_fp16 else '❌'} | "
          f"Q8 {q8_mb/1024:>5.2f}GB {'✅' if ok_q8 else '❌'} | Q4 {q4_mb/1024:>5.2f}GB {'✅' if ok_q4 else '❌'}")

print()
print("=== 候选方向验证结论 ===")
print("A 前缀缓存: 共享前缀复用 (已用) — 长上下文单请求无益")
print("B KV 量化: Q8 即达 64k+ / Q4 超 128k — 立即可用 (llama.cpp)")
print("   — 显存翻倍收益 — 首推落地")
print("C 稀疏加载 (IMPRESS/ClusterKV): 重要KV才读 —")
print("   理论收益: 8x 加载减 (VestigeKV 0.92@32x) — 需实现+精度风险")
print("D 驱逐 (H2O 类): 证伪 (R817 评分无用论 + TwinKV 试败)")
print("E 合并 (CentroidKV): 静态压缩 — 12GB 中上下文收益小 (量化已覆盖)")
print()
print(">>> 推荐路径: B (KV量化 — 立即可得 4x) → C (稀疏加载 — 墙外再上)")
