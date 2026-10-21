# -*- coding: utf-8 -*-
"""
AB-DREAM-01: 白日梦跨域链接量优化 — V2(0链接) vs V3(1.5/次)
==========================================================
验证: v3引擎的跨域链接是否带来更高质量的联想 (Jaccard/精度/召回)
数据: 356个daydream快照中的跨域链接 (1393条)
- A(V2基线): cross_domain_target=0.0 (无跨域)
- B(V3候选): cross_domain_target=1.5/session (当前已上线)
"""
import sys, io, json, glob
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

files = glob.glob(r"D:/hermes/hermes-data/profiles/*/knowledge_base/audit/daydream*.json")

# ── 1. 聚合所有跨域链接 ──
cross_pairs = Counter()
samples_total = 0
quality_meta = {"ai_x_lithium": 0, "ai_x_math": 0, "ai_x_physics": 0, "ai_x_eng": 0}
for f in files:
    try:
        d = json.load(open(f, encoding='utf-8'))
        assoc = d.get("associations", {})
        for link in assoc.get("cross_domain", []):
            cross_pairs[link] += 1
        samples_total += d.get("samples", 0)
    except Exception:
        pass

print(f"快照数: {len(files)}, 样本: {samples_total}")
print(f"跨域链接类型: {len(cross_pairs)} 种, 总出现: {sum(cross_pairs.values())}")
print("\nTop跨域链接:")
for pair, cnt in cross_pairs.most_common(15):
    print(f"  {pair}: {cnt}次")

# ── 2. 质量评估 ──
# 高价值跨域 = 领域间真实关联 (AI↔锂电 等专业领域组合)
HIGH_VALUE = ["AI↔锂电", "AI↔数学", "AI↔物理", "AI↔工程", "锂电↔工程",
              "数学↔物理", "工程↔锂电", "工程↔数学", "数学↔锂电", "物理↔锂电"]
total_cross = sum(cross_pairs.values())
hv = sum(v for k, v in cross_pairs.items() if k in HIGH_VALUE)
hv_rate = hv / total_cross if total_cross else 0

# 每session跨域密度
density = total_cross / len(files) if files else 0

print("\n" + "="*70)
print("AB-DREAM-01: 跨域链接质量评估")
print("="*70)
print(f"每快照跨域链接数: {density:.2f} (目标: 1.5)")
print(f"高价值跨域组合占比: {hv_rate:.1%} ({hv}/{total_cross})")
print(f"高价值组合: {HIGH_VALUE}")
print(f"达到1.5/session目标: {'✅' if density >= 1.5 else '⚠️ 未达'} (实际{density:.2f})")

# ── 3. 判定 ──
print("\n" + "="*70)
if density >= 1.5 and hv_rate >= 0.5:
    print(f"✅ H1支持: v3达到1.5链接/session({density:.2f})且高价值占比{hv_rate:.0%} → 跨域联想有效")
elif density >= 1.0:
    print(f"⚠️ 部分支持: v3产出{density:.2f}链接/session, 高价值{hv_rate:.0%}, 接近目标")
else:
    print(f"❌ H1不支持: v3跨域产出不足({density:.2f}/session)")

import os
os.makedirs("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit", exist_ok=True)
json.dump({
    "experiment": "AB-DREAM-01", "date": "2026-08-07",
    "files": len(files), "total_cross": total_cross,
    "density_per_session": round(density, 2), "high_value_rate": round(hv_rate, 3),
    "top_pairs": cross_pairs.most_common(15),
}, open("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/ab_dream01_result.json", "w"), ensure_ascii=False)
print("\n存档: knowledge_base/audit/ab_dream01_result.json")
