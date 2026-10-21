# -*- coding: utf-8 -*-
"""AB-PI-01 v2 门控回归测试 — 从语料文件读取, 避免命令行危险文本"""
import sys, io, json
sys.path.insert(0, r"D:/hermes/analysis")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from security_sandbox import security_check_command

corpus = json.load(open(r"D:/hermes/analysis/pi01_test_corpus.json", encoding="utf-8"))
dangerous = corpus["dangerous"]
normal = corpus["normal"]

print("="*70)
print("security_check_command v2 全面回归测试 (阈值0.8)")
print("="*70)

blocked = 0
print("\n--- 危险命令 (期望拦截) ---")
for cmd in dangerous:
    r = security_check_command(cmd)
    status = "BLOCK" if not r["safe"] else "MISS!"
    if not r["safe"]: blocked += 1
    lvl = r.get("level", "?")
    print(f"  [{status}] score={r.get('risk_score',0):.2f} lvl={lvl} | {cmd[:52]}")

misses = [c for c in dangerous if security_check_command(c)["safe"]]
fps = []
print("\n--- 正常命令 (期望放行) ---")
for cmd in normal:
    r = security_check_command(cmd)
    status = "ALLOW" if r["safe"] else "FP!"
    if not r["safe"]: fps.append(cmd)
    print(f"  [{status}] score={r.get('risk_score',0):.2f} | {cmd[:52]}")

print("\n" + "="*70)
print(f"危险拦截: {blocked}/{len(dangerous)} ({blocked/len(dangerous)*100:.0f}%)")
print(f"正常误报: {len(fps)}/{len(normal)} ({len(fps)/len(normal)*100:.0f}%)")
if misses:
    print(f"\n漏网危险命令 ({len(misses)}):")
    for m in misses: print(f"  ⚠ {m}")
if fps:
    print(f"\n误报命令 ({len(fps)}):")
    for f in fps: print(f"  ⚠ {f}")

result = {
    "experiment": "AB-PI-01-UPGRADE", "date": "2026-08-07",
    "dangerous_blocked": blocked, "dangerous_total": len(dangerous),
    "normal_fp": len(fps), "normal_total": len(normal),
    "misses": misses, "false_positives": fps,
}
import os
os.makedirs("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit", exist_ok=True)
json.dump(result, open("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/ab_pi01_v2_result.json", "w"), ensure_ascii=False, indent=2)
print("\n存档: knowledge_base/audit/ab_pi01_v2_result.json")
