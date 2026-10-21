# -*- coding: utf-8 -*-
"""
AB-SLEEP-02: 睡眠 promote 阈值渐进搜索 — 18/20/22/24/25%
========================================================
从18%→25%以2%步进, 找到边际收益=边际成本点。
AB-SLEEP-01结论: 22%比18%更差(F1 0.698 vs 0.718) → 重点观察20%附近是否有峰值。
"""
import sys, io, sqlite3
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB = "D:/hermes/hermes-data/profiles/qqbot3/state.db"

HIGHLY = ["定理","证明","蒸馏","attention","涂布","coating","KV","算法","theorem",
          "proof","architecture","agent","memory","安全","漏洞","模型","拓扑","evolution"]
NOISE = ["通联网关健康","偏差-方差路由","okf-daily","cron","gateway health",
         "watchdog","巡检","每6h更新","silent","hello"]

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
print(f"真实记忆池: {len(pool)} 条 (高价值{sum(p['label'] for p in pool)})")

def importance(text):
    t = text.lower()
    pos = sum(min(2, t.count(k)) for k in HIGHLY)
    noi = sum(t.count(n) for n in NOISE)
    s = 0.1 + pos*0.35 - noi*0.25
    return max(0.0, min(1.0, s))

def classify(promote_pct, discard_th, pool):
    scored = sorted(pool, key=lambda p: importance(p["text"]), reverse=True)
    n_promote = int(len(scored)*promote_pct/100)
    promote_ids = set(id(p) for p in scored[:n_promote])
    discard_ids = set()
    for p in scored[n_promote:]:
        if importance(p["text"]) < discard_th:
            discard_ids.add(id(p))
    return promote_ids, discard_ids

def evaluate_F1(promote_ids, discard_ids, pool):
    tp=fp=tn=fn=0
    for p in pool:
        pid = id(p)
        kept = pid in promote_ids
        if kept and pid in discard_ids:
            kept = False
        if kept and p["label"]: tp+=1
        elif not kept and not p["label"]: tn+=1
        elif kept and not p["label"]: fp+=1
        else: fn+=1
    prec = tp/(tp+fp) if tp+fp else 0
    rec = tp/(tp+fn) if tp+fn else 0
    f1 = 2*prec*rec/(prec+rec) if prec+rec else 0
    return f1, prec, rec

print("\n" + "="*70)
print("AB-SLEEP-02: promote 阈值渐进搜索 (18/20/22/24/25%)")
print("="*70)

thresholds = [18, 20, 22, 24, 25]
results = []
for th in thresholds:
    p, d = classify(th, 0.10, pool)
    f1, prec, rec = evaluate_F1(p, d, pool)
    prom = len(p)/len(pool)*100
    disc = len(d)/len(pool)*100
    results.append({"th": th, "F1": f1, "prec": prec, "rec": rec, "promote": prom, "discard": disc})
    print(f"promote={th}%: F1={f1:.3f} prec={prec:.3f} rec={rec:.3f} promote={prom:.1f}% discard={disc:.1f}%")

# 找最优 + 边际分析
best = max(results, key=lambda r: r["F1"])
print("\n" + "="*70)
print(f"最优阈值: {best['th']}% (F1={best['F1']:.3f})")

# 边际收益分析 (每+2%的F1变化)
print("\n边际分析 (每步进2%的F1增益):")
for i in range(1, len(results)):
    delta = (results[i]["F1"] - results[i-1]["F1"]) * 100
    print(f"  {results[i-1]['th']}%→{results[i]['th']}%: {delta:+.2f}pp {'📈' if delta>0 else '📉'}")

# 结论
print("\n" + "="*70)
if best["th"] == 18:
    print(f"❌ 结论: 18%仍最优 — 现有配置已接近边际最优, 不建议提高promote")
elif best["th"] == 20:
    print(f"✅ 结论: 20%是最优 — 相比当前18%有提升, 建议微调至20%")
else:
    print(f"✅ 结论: {best['th']}%最优 — 相比当前18%有提升空间")

import json, os
os.makedirs("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit", exist_ok=True)
json.dump({
    "experiment": "AB-SLEEP-02", "date": "2026-08-07",
    "results": results, "best": best["th"],
}, open("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/ab_sleep02_result.json", "w"), ensure_ascii=False)
print("\n存档: knowledge_base/audit/ab_sleep02_result.json")
