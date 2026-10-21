# -*- coding: utf-8 -*-
"""
AB-DREAM-02: 白日梦链接质量阈值调优 — 0.7/0.8/0.9/0.95
=====================================================
依赖AB-DREAM-01结果(v3已产出3.91链接/session)。
假设: 质量阈值0.8时 J(F1) 最优 — precision/recall平衡。
用高价值组合占比作为质量信号, 模拟不同阈值下的取舍。
"""
import sys, io, json, glob
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

files = glob.glob(r"D:/hermes/hermes-data/profiles/*/knowledge_base/audit/daydream*.json")

# 高价值组合 (领域间真实关联)
HIGH_VALUE = {"AI↔锂电", "AI↔数学", "AI↔物理", "AI↔工程", "锂电↔工程",
              "数学↔物理", "工程↔锂电", "工程↔数学", "数学↔锂电", "物理↔锂电"}
# 低价值组合 (宽泛无信息量)
LOW_VALUE = {"AI↔AI", "锂电↔锂电", "通用↔通用", "其他↔其他", "AI↔通用", "通用↔AI"}

cross_pairs = Counter()
total_samples = 0
for f in files:
    try:
        d = json.load(open(f, encoding='utf-8'))
        assoc = d.get("associations", {})
        for link in assoc.get("cross_domain", []):
            cross_pairs[link] += 1
        total_samples += d.get("samples", 0)
    except Exception:
        pass

total = sum(cross_pairs.values())
# 每条链接的"质量分": 高价值=0.95 中等=0.8 低价值=0.5 (模拟)
def link_quality(link):
    if link in HIGH_VALUE: return 0.95
    if link in LOW_VALUE: return 0.5
    return 0.8

print(f"总链接: {total}")

# 模拟不同阈值: 只保留质量 >= 阈值的链接
def evaluate(threshold):
    kept = [(k, v) for k, v in cross_pairs.items() if link_quality(k) >= threshold]
    kept_cnt = sum(v for _, v in kept)
    # precision: 保留中的高价值占比; recall: 高价值被保留率
    hv_kept = sum(v for k, v in kept if k in HIGH_VALUE)
    hv_total = sum(v for k, v in cross_pairs.items() if k in HIGH_VALUE)
    prec = hv_kept / kept_cnt if kept_cnt else 0
    rec = hv_kept / hv_total if hv_total else 0
    f1 = 2*prec*rec/(prec+rec) if prec+rec else 0
    return {"threshold": threshold, "kept": kept_cnt, "precision": round(prec,3),
            "recall": round(rec,3), "F1": round(f1,3)}

print("\n" + "="*70)
print("AB-DREAM-02: 链接质量阈值调优 (0.7/0.8/0.9/0.95)")
print("="*70)
results = []
for th in [0.5, 0.7, 0.8, 0.9, 0.95]:
    r = evaluate(th)
    results.append(r)
    print(f"阈值{th:.2f}: 保留{r['kept']}条 prec={r['precision']} rec={r['recall']} F1={r['F1']}")

best = max(results, key=lambda r: r["F1"])
print("\n" + "="*70)
print(f"最优阈值: {best['threshold']:.2f} (F1={best['F1']})")
if best["threshold"] == 0.8:
    print("✅ H1支持: 阈值0.8时J(F1)最优 — 与假设一致")
else:
    print(f"⚠️ 假设H1(0.8最优)未完全验证, 实际最优在{best['threshold']:.2f}")

import os
os.makedirs("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit", exist_ok=True)
json.dump({
    "experiment": "AB-DREAM-02", "date": "2026-08-07",
    "results": results, "best_threshold": best["threshold"],
}, open("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/ab_dream02_result.json", "w"), ensure_ascii=False)
print("\n存档: knowledge_base/audit/ab_dream02_result.json")
