#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""睡眠三轨 A/B 分析 (三周三配置: 单轨/双轨/三轨 — 2026-09-06 启动)
周1 09-07~09-14: 单轨 V2 (RECON+纺锤停)
周2 09-14~09-21: 双轨 V2+RECON (纺锤停)
周3 09-21~09-28: 三轨 V2+RECON+纺锤
对比: V2 promote/discard/阈值 + RECON/纺锤存在期的记忆指标
"""
# side_effects: [只读+报告]
import json
import glob
import os
from datetime import datetime

OUT = r"D:\hermes\hermes-data\profiles\qqbot3\knowledge_base\audit"

WEEKS = {
    "周1单轨(09-07~14)": ("2026-09-07", "2026-09-14"),
    "周2双轨(09-14~21)": ("2026-09-14", "2026-09-21"),
    "周3三轨(09-21~28)": ("2026-09-21", "2026-09-28"),
}


def collect_v2():
    rows = []
    for f in sorted(glob.glob(os.path.join(OUT, "sleep_v2_*.json"))):
        name = os.path.basename(f).replace("sleep_v2_", "").replace(".json", "")
        if len(name) < 12 or not name[:8].isdigit():
            continue
        try:
            d = json.load(open(f, encoding="utf-8"))
            ab = d.get("ab_metrics", {})
            rows.append({"date": name[:8], "promote": ab.get("v2_promote_rate"),
                         "discard": ab.get("v2_discard_rate"),
                         "cluster": ab.get("jaccard_clusters"),
                         "thr": ab.get("promote_threshold")})
        except Exception:
            pass
    return rows


def week_stats(rows, start, end):
    wk = [r for r in rows if start <= r["date"] < end]
    if not wk:
        return None
    return {"n": len(wk),
            "promote_avg": round(sum(r["promote"] for r in wk) / len(wk), 3),
            "discard_avg": round(sum(r["discard"] for r in wk) / len(wk), 3),
            "cluster_avg": round(sum(r["cluster"] for r in wk) / len(wk), 1),
            "thr_last": wk[-1]["thr"]}


def main():
    rows = collect_v2()
    print("=" * 55)
    print("睡眠三轨 A/B — 周对比 (V2 主指标)")
    print("=" * 55)
    results = {}
    for label, (s, e) in WEEKS.items():
        st = week_stats(rows, s, e)
        if st:
            print(f"\n{label}: {st['n']} 次 V2 运行")
            print(f"  promote 均值 {st['promote_avg']} | discard 均值 {st['discard_avg']}")
            print(f"  簇数 {st['cluster_avg']} | 末阈值 {st['thr_last']}")
            results[label] = st
        else:
            print(f"\n{label}: 无数据 (窗口未到/未跑)")
            results[label] = {"n": 0}
    # 历史参考 (三轨期 09-01~06)
    pre = week_stats(rows, "2026-08-25", "2026-09-07")
    if pre:
        print(f"\n[参考] A/B 前混合期 (08-25~09-06): promote {pre['promote_avg']} | discard {pre['discard_avg']}")
    rep = {"ts": datetime.now().isoformat(), "results": results, "pre": pre}
    rp = os.path.join(OUT, "sleep_three_track_ab_20260929.json")
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(f"\n报告: {rp}")


if __name__ == "__main__":
    main()
