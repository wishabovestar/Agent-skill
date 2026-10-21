# -*- coding: utf-8 -*-
"""
AB-SLEEP-01: 睡眠 promote 阈值优化 — 18% vs 22%
=================================================
数据: 真实会话 (state.db)
场景: 记忆分类 (promote到长期 / keep短时 / discard噪声)
指标: F1 (保留高价值质量 + 丢噪声质量), promote_rate, discard_rate
"""
import sys, io, sqlite3, collections
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB = "D:/hermes/hermes-data/profiles/qqbot3/state.db"

# 高价值/噪声词
HIGHLY = ["定理","证明","蒸馏","attention","涂布","coating","KV","算法","theorem",
          "proof","architecture","agent","memory","安全","漏洞","模型","拓扑","evolution"]
NOISE = ["通联网关健康","偏差-方差路由","okf-daily","cron","gateway health",
         "watchdog","巡检","每6h更新","silent","hello"]

# ── 1. 加载真实会话 ──
conn = sqlite3.connect(DB)
rows = conn.execute("""
   SELECT s.title, m.content FROM sessions s 
   LEFT JOIN (SELECT session_id, MAX(id) mid FROM messages GROUP BY session_id) mm ON mm.session_id=s.id
   LEFT JOIN messages m ON m.id=mm.mid
   WHERE s.archived=0 ORDER BY s.rowid DESC LIMIT 500
""").fetchall()
conn.close()

pool = []
for title, content in rows:
    text = (title or '') + ' ' + (content or '')
    if not text.strip(): continue
    is_noise = any(n in (title or '') for n in NOISE)
    is_val = any(k.lower() in text.lower() for k in HIGHLY) and not is_noise
    pool.append({"text": text[:1000], "label": 1 if is_val else 0, "title": (title or '')[:30]})
print(f"真实记忆池: {len(pool)} 条 (高价值{sum(p['label'] for p in pool)}/噪声)")

# ── 2. 重要性评分 (sleep_memory逻辑) ──
def importance(text):
    t = text.lower()
    pos = sum(min(2, t.count(k)) for k in HIGHLY)
    noi = sum(t.count(n) for n in NOISE)
    s = 0.1 + pos*0.35 - noi*0.25
    return max(0.0, min(1.0, s))

# ── 3. 分类器 (promote/discard阈值) ──
def classify(params, pool):
    """params: [promote_rate_pct, discard_threshold] → 分配记忆"""
    promote_pct, discard_th = params
    scored = sorted(pool, key=lambda p: importance(p["text"]), reverse=True)
    # promote: 取前 promote_pct% 
    n_promote = int(len(scored)*promote_pct/100)
    promote_ids = set(id(p) for p in scored[:n_promote])
    # discard: 分 < discard_th 且不在promote
    discard_ids = set()
    for p in scored[n_promote:]:
        if importance(p["text"]) < discard_th:
            discard_ids.add(id(p))
    return promote_ids, discard_ids

def evaluate_F1(promote_ids, discard_ids, pool):
    tp=fp=tn=fn=0
    for p in pool:
        pid = id(p)
        kept = pid in promote_ids        # 保留(含promote; discard视为丢弃)
        if kept and pid in discard_ids:  # 冲突: discard优先
            kept = False
        if kept and p["label"]: tp+=1
        elif not kept and not p["label"]: tn+=1
        elif kept and not p["label"]: fp+=1
        else: fn+=1
    prec = tp/(tp+fp) if tp+fp else 0
    rec = tp/(tp+fn) if tp+fn else 0
    f1 = 2*prec*rec/(prec+rec) if prec+rec else 0
    return f1, prec, rec, tp, fp

# ── 4. AB 对比 ──
print("\n" + "="*66)
print("AB-SLEEP-01: promote 阈值 18% vs 22%")
print("="*66)

# A: promote=18%, discard=0.1
pa = (18, 0.10)
pA, dA = classify(pa, pool)
f1A, precA, recA, tpA, fpA = evaluate_F1(pA, dA, pool)
promA = len(pA)/len(pool)*100; discA = len(dA)/len(pool)*100

# B: promote=22%, discard=0.1
pb = (22, 0.10)
pB, dB = classify(pb, pool)
f1B, precB, recB, tpB, fpB = evaluate_F1(pB, dB, pool)
promB = len(pB)/len(pool)*100; discB = len(dB)/len(pool)*100

print(f"\n{'指标':<14} | {'A:promote18%':>12} | {'B:promote22%':>12} | 差异")
print(f"{'F1':<14} | {f1A:>12.3f} | {f1B:>12.3f} | {(f1B-f1A)*100:+.1f}pp")
print(f"{'precision':<14} | {precA:>12.3f} | {precB:>12.3f}")
print(f"{'recall':<14} | {recA:>12.3f} | {recB:>12.3f}")
print(f"{'promote率':<14} | {promA:>12.1f}% | {promB:>12.1f}%")
print(f"{'discard率':<14} | {discA:>12.1f}% | {discB:>12.1f}%")
print(f"{'TP/FP':<14} | {tpA}/{fpA:>8} | {tpB}/{fpB:>8}")

# ── 5. 结论 ──
improve = (f1B - f1A) * 100
print("\n" + "="*66)
if f1B > f1A:
    print(f"✅ H1支持: promote=22%时 F1={f1B:.3f} > 当前A F1={f1A:.3f} (+{improve:.1f}pp)")
elif abs(f1B-f1A) < 0.01:
    print(f"⚠️ 差异不显著: F1均≈{f1A:.3f}, 22%未带来明显提升")
else:
    print(f"❌ H1不支持: promote=22% F1={f1B:.3f} < 18% F1={f1A:.3f} ({improve:.1f}pp)")
# 检查 discard 是否 <10% (假设条件)
print(f"  检查discard<10%: A={discA:.1f}% {'✅' if discA<10 else '❌'}  B={discB:.1f}% {'✅' if discB<10 else '❌'}")

import json, os
os.makedirs("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit", exist_ok=True)
json.dump({
    "experiment":"AB-SLEEP-01","date":"2026-08-02",
    "A_promote18":{"F1":f1A,"prec":precA,"rec":recA,"promote":promA,"discard":discA},
    "B_promote22":{"F1":f1B,"prec":precB,"rec":recB,"promote":promB,"discard":discB},
    "improve_pp":round(improve,2),
}, open("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/ab_sleep01_result.json","w"), ensure_ascii=False)
print(f"\n存档: knowledge_base/audit/ab_sleep01_result.json")
