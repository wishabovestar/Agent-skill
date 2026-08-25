# -*- coding: utf-8 -*-
"""基因周度研究轮 (2026-08-23 重建)
功能: 评分排序 + 解锁推荐 (cron 8c4079a319f5)
规则: status=锁 跳过 (不参与推荐, 防重复踩坑)
评分: effort/hw/data/time 加权 (gene_score_ab 方法)
"""
import json
import os
import sys

POOL = os.path.join(os.path.dirname(__file__), "..", "data", "gene_pool.json")

EFFORT = {"低": 1, "中": 2, "高": 3}
HW = {"有": 1, "部分": 0.5, "无": 0}
DATA = {"有": 1, "部分": 0.5, "无": 0}
TIME = {"快": 1, "中": 0.5, "慢": 0.25}


def score(g):
    """解锁可行性评分: 资源可及性 × 数据完备性 (0-10)"""
    s = 0.0
    s += (4 - EFFORT.get(g.get("effort", "高"), 3)) * 1.5      # 低 effort 高分
    s += HW.get(g.get("hw", "无"), 0) * 1.5                     # 硬件可及
    s += DATA.get(g.get("data", "无"), 0) * 1.5                 # 数据完备
    s += TIME.get(g.get("time", "慢"), 0.25) * 1.5              # 时间快
    s += 1.0 if g.get("unlock") else 0.0                        # 有解锁路径
    return round(min(s, 10), 2)


def main():
    pool = json.load(open(POOL, encoding="utf-8"))
    genes = pool.get("genes", [])

    locks = [g for g in genes if g.get("status") == "锁"]
    actives = [g for g in genes if g.get("status") in ("基因", "候选")]

    # 排序: 候选/基因 按评分
    ranked = sorted(actives, key=score, reverse=True)

    print("=" * 56)
    print("基因周度研究轮 (评分排序 + 解锁推荐)")
    print("=" * 56)
    print(f"基因 {len(genes)} | 活跃 {len(actives)} | 锁 {len(locks)} (跳过)\n")

    print("## 活跃基因评分排序 (Top 5)")
    for i, g in enumerate(ranked[:5], 1):
        s = score(g)
        print(f"  {i}. [{g.get('status')}] {g['name']} 评分={s}")
        if g.get("unlock"):
            print(f"     unlock: {g['unlock']}")

    print("\n## 解锁推荐 (优先候选)")
    recs = [g for g in ranked if g.get("status") == "候选"][:3]
    if not recs:
        recs = ranked[:3]
    for g in recs:
        print(f"  ▶ {g['name']} (评分={score(g)})")
        print(f"    block: {g.get('block', '')[:80]}")

    print("\n## 基因锁 (不参与推荐 — 防重复踩坑)")
    for g in locks:
        print(f"  🔒 {g['name']} (unlock: {g.get('unlock', '无')[:60]})")

    print("\n## 解锁可行性再评估 (锁状态可解锁?)")
    for g in locks:
        s = score(g)
        if s >= 7:
            print(f"  ⚡ {g['name']} 评分={s} — 建议评估解锁")
    print("\n完成")


if __name__ == "__main__":
    main()
