#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""白日梦 v1 vs v3 A/B 结果分析 (2026-09-06 启动, 48h 后 09-08 运行)
窗口: 2026-09-06T09:00 ~ 2026-09-08T09:00
对比维度 (产物质量评分):
  v1 (每2h轻量) vs v3 (每日02:00深度)
  ① 洞察量: 压缩机会/关联/跨域发现 每产物数
  ② 噪声率: 技能高频词命中停用词后残余模板词比例
  ③ 可行动性: 建议含具体会话引用+类型的比例
  ④ 运行成本: 时长/会话扫描数
输出: 评分+推荐版本
"""
# side_effects: [只读+报告写入]
import json
import glob
import os
import re
from datetime import datetime

OUT = r"D:\hermes\hermes-data\profiles\qqbot3\knowledge_base\audit"
WINDOW_START = "2026-09-06T09:00"
WINDOW_END = "2026-09-08T09:00"

TEMPLATE_NOISE = {"output", "job", "final", "response", "use", "tool", "result",
                  "step", "return", "print", "input", "value", "data", "time",
                  "work", "done", "task", "user", "agent", "sep", "run", "you",
                  "content", "important", "内容", "工作", "输出含"}


def in_window(ts_str, start, end):
    try:
        ts = datetime.fromisoformat(ts_str)
        return start <= ts.isoformat() <= end
    except Exception:
        return False


def analyze_v1(files):
    stats = {"n": 0, "compress": 0, "compress_with_ref": 0, "noise_terms": [],
             "cross_domains": set(), "total_terms": 0}
    for f in files:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not in_window(d.get("timestamp", ""), WINDOW_START, WINDOW_END):
            continue
        stats["n"] += 1
        comp = d.get("compression_suggestions", [])
        stats["compress"] += len(comp)
        stats["compress_with_ref"] += sum(1 for c in comp if c.get("session"))
        for s in d.get("skill_suggestions", []):
            for t in s.get("tech_terms", []) + s.get("cn_terms", []):
                stats["total_terms"] += 1
                if t.lower() in TEMPLATE_NOISE:
                    stats["noise_terms"].append(t)
        for assoc in d.get("associations", {}).get("cross_domain", []):
            stats["cross_domains"].add(assoc)
    return stats


def analyze_v3(files):
    stats = {"n": 0, "ideas": 0, "concepts": 0, "has_cross": 0, "sessions": 0}
    for f in files:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not in_window(d.get("timestamp", ""), WINDOW_START, WINDOW_END):
            continue
        stats["n"] += 1
        stats["ideas"] += len(d.get("ideas", []))
        stats["concepts"] += len(d.get("concepts", []))
        stats["sessions"] += d.get("sessions_analyzed", 0)
        # idea 可行动性: 含跨域组合标记
        for idea in d.get("ideas", []):
            txt = json.dumps(idea, ensure_ascii=False)
            if re.search(r"用|结合|优化|提升|方法", txt):
                stats["has_cross"] += 1
    return stats


def main():
    v1_files = sorted(glob.glob(os.path.join(OUT, "daydream_2026090[678]*.json")))
    v3_files = sorted(glob.glob(os.path.join(OUT, "daydream_v3_2026090[678]*.json")))
    s1 = analyze_v1(v1_files)
    s3 = analyze_v3(v3_files)

    print("=" * 55)
    print(f"白日梦 A/B 分析窗口: {WINDOW_START} ~ {WINDOW_END}")
    print("=" * 55)
    print(f"\n[v1 轻量] 产物 {s1['n']} | 压缩建议 {s1['compress']} (带引用 {s1['compress_with_ref']})")
    if s1["total_terms"]:
        noise_rate = len(s1["noise_terms"]) / s1["total_terms"]
    else:
        noise_rate = 0
    print(f"  噪声词率: {noise_rate:.1%} | 残余噪声: {sorted(set(s1['noise_terms']))[:6]}")
    print(f"  跨域发现: {s1['cross_domains'] if s1['cross_domains'] else '无'}")
    per = s1["compress"] / s1["n"] if s1["n"] else 0
    print(f"  每产物洞察: {per:.1f}")

    print(f"\n[v3 深度] 产物 {s3['n']} | ideas {s3['ideas']} | 概念 {s3['concepts']}")
    print(f"  扫描会话: {s3['sessions']} | 可行动 idea: {s3['has_cross']}")
    print(f"  每产物 idea: {s3['ideas'] / s3['n'] if s3['n'] else 0:.1f}")

    # 评分 (归一化 0-10)
    v1_score = min(10, per * 2 + (1 - noise_rate) * 5)
    v3_score = min(10, (s3["ideas"] / s3["n"] if s3["n"] else 0) * 3 + s3["has_cross"])
    print(f"\n评分: v1={v1_score:.1f} | v3={v3_score:.1f}")
    winner = "v3 深度 (洞察质量优先)" if v3_score >= v1_score else "v1 轻量 (频次覆盖优先)"
    print(f"\n>>> 推荐: {winner}")
    print("  注: v1 优势=覆盖频次/实时性 | v3 优势=洞察深度/低噪声")
    print("  若评分接近: 保留双轨 (v1 快照 + v3 每日深度) 是合理终态")

    # 报告保存
    s1_out = dict(s1)
    s1_out["cross_domains"] = sorted(s1_out["cross_domains"])
    s3_out = dict(s3)
    rep = {"window": [WINDOW_START, WINDOW_END], "v1": s1_out, "v3": s3_out,
           "score": {"v1": round(v1_score, 2), "v3": round(v3_score, 2)},
           "recommend": winner, "ts": datetime.now().isoformat()}
    rp = os.path.join(OUT, "daydream_ab_20260908.json")
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(f"\n报告: {rp}")


if __name__ == "__main__":
    main()
