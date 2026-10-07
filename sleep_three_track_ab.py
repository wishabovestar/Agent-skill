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
import sys
from datetime import datetime

OUT = r"D:\hermes\hermes-data\profiles\qqbot3\knowledge_base\audit"

WEEKS = {
    "周1单轨(09-07~14)": ("2026-09-07", "2026-09-14"),
    "周2双轨(09-14~21)": ("2026-09-14", "2026-09-21"),
    "周3三轨(09-21~28)": ("2026-09-21", "2026-09-28"),
}


def _iso(compact: str) -> str:
    """'YYYYMMDD' → 'YYYY-MM-DD'。

    ★ 2026-09-29 修 (hotfix): 文件名的日期是紧凑格式 (name[:8] = '20260922'), 而 WEEKS 的周界是
    带连字符格式 ('2026-09-21')。直接做字符串比较时, 第 5 个字符 '0' (0x30) > '-' (0x2D)
    ⇒ `compact < end` 恒为 False ⇒ 三个窗口全部命中 0 ⇒ 静默输出「无数据」而源文件齐全。
    凡「从文件名抠日期 + 与配置周界比较」都必须先归一格式。
    """
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"


def collect_v2():
    rows = []
    for f in sorted(glob.glob(os.path.join(OUT, "sleep_v2_*.json"))):
        name = os.path.basename(f).replace("sleep_v2_", "").replace(".json", "")
        if len(name) < 12 or not name[:8].isdigit():
            continue
        try:
            d = json.load(open(f, encoding="utf-8"))
            ab = d.get("ab_metrics", {})
            rows.append({"date": name[:8], "file": os.path.basename(f),
                         "promote": ab.get("v2_promote_rate"),
                         "discard": ab.get("v2_discard_rate"),
                         "cluster": ab.get("jaccard_clusters"),
                         "thr": ab.get("promote_threshold")})
        except Exception:
            pass
    return rows


def week_stats(rows, start, end):
    wk = [r for r in rows if start <= _iso(r["date"]) < end]
    bad = [r for r in wk if any(r[k] is None for k in ("promote", "discard", "cluster", "thr"))]
    if bad:
        print(f"  ⚠️ 窗口 {start}~{end} 内有 {len(bad)} 份报告缺 ab_metrics 字段 (不计入): "
              f"{[r['file'] for r in bad]}")
        wk = [r for r in wk if r not in bad]
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
    src = sorted(_iso(r["date"]) for r in rows)
    print(f"源文件: {len(rows)} 份 sleep_v2_*.json | 日期跨度 {src[0] if src else '-'} ~ {src[-1] if src else '-'}")
    if not rows:
        print("🔴 未解析到任何 sleep_v2_*.json —— 无法分析 (退出码 1, 非'无数据')")
        sys.exit(1)
    results = {}
    for label, (s, e) in WEEKS.items():
        st = week_stats(rows, s, e)
        if st:
            print(f"\n{label}: {st['n']} 次 V2 运行")
            print(f"  promote 均值 {st['promote_avg']} | discard 均值 {st['discard_avg']}")
            print(f"  簇数 {st['cluster_avg']} | 末阈值 {st['thr_last']}")
            inwin = [r for r in rows if s <= _iso(r["date"]) < e]
            print("  样本明细 (判'对称比较'前必看):")
            for r in inwin:
                print(f"    {_iso(r['date'])} {r['file']:32s} promote={r['promote']} "
                      f"discard={r['discard']} cluster={r['cluster']} thr={r['thr']}")
            results[label] = st
        else:
            near = [r["file"] for r in rows if abs(int(_iso(r["date"]).replace("-", "")) -
                    int(s.replace("-", ""))) < 300]
            print(f"\n{label}: ⚠️ 窗口内 0 样本 (源日期 {s}~{e} 无命中; 邻近样本={near})")
            results[label] = {"n": 0}
    # 历史参考 (三轨期 09-01~06)
    pre = week_stats(rows, "2026-08-25", "2026-09-07")
    if pre:
        print(f"\n[参考] A/B 前混合期 (08-25~09-06): promote {pre['promote_avg']} | discard {pre['discard_avg']}")
    rep = {"ts": datetime.now().isoformat(), "results": results, "pre": pre,
           "src_files": len(rows)}
    rp = os.path.join(OUT, f"sleep_three_track_ab_{datetime.now():%Y%m%d}.json")
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(f"\n报告: {rp}")
    print("\n★ 报告纪律: promote/discard 两列在阈值型自指下不含测量信息 ⇒ 结论须先过 "
          "dream_engine_health.py ⑤ 段有效性门; 样本数不等 (手工跑混入) ⇒ 不作对称比较。")


if __name__ == "__main__":
    main()
