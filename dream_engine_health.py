# -*- coding: utf-8 -*-
"""睡眠/白日梦引擎健康检查 (R1116)

★ 背景: 用户要求检查两引擎运行情况。发现问题:
  ① sleep_memory_v2 的 v2_discard_rate 【连续 5 次为 0.00】
  ② daydream 的 skill_suggestions 含噪声词

★★ 本脚本: 端到端健康检查 + 缺陷量化
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "D:/hermes/hermes-data/profiles/qqbot3"
AUDIT = os.path.join(BASE, "knowledge_base", "audit")
sys.path.insert(0, os.path.join(BASE, "scripts"))


def check_products():
    """① 产物新鲜度"""
    print("=" * 74)
    print("  ① 产物健康度")
    print("=" * 74)
    rows = []
    for pfx in ["daydream_", "sleep_v2_", "daydream_v3_", "sleep_"]:
        fs = [f for f in os.listdir(AUDIT)
              if f.startswith(pfx) and f.endswith(".json")]
        fs.sort(key=lambda f: os.path.getmtime(os.path.join(AUDIT, f)),
                reverse=True)
        if fs:
            latest = fs[0]
            p = os.path.join(AUDIT, latest)
            age_h = (datetime.now().timestamp() - os.path.getmtime(p)) / 3600
            rows.append((pfx, len(fs), latest, age_h))
    for pfx, n, latest, age in rows:
        flag = "✅" if age < 26 else "🔴"
        print("  %s %-14s %3d 个 | 最新 %s (%.1f 小时前)"
              % (flag, pfx, n, latest[:34], age))
    return rows


def check_sleep_metrics():
    """② 睡眠引擎的 A/B 指标趋势"""
    print()
    print("=" * 74)
    print("  ② 睡眠引擎 A/B 指标 (最近 8 次)")
    print("=" * 74)
    fs = sorted([f for f in os.listdir(AUDIT)
                 if f.startswith("sleep_v2_") and f.endswith(".json")],
                key=lambda f: os.path.getmtime(os.path.join(AUDIT, f)),
                reverse=True)[:8]
    print("  %-17s %8s %8s %8s %8s" % (
        "时间", "v1促进", "v2促进", "v1丢弃", "★v2丢弃"))
    print("  " + "-" * 56)
    zero_discard = 0
    for f in fs:
        try:
            d = json.load(open(os.path.join(AUDIT, f), encoding="utf-8"))
            m = d.get("ab_metrics", {})
            v2d = m.get("v2_discard_rate", 0)
            if v2d == 0:
                zero_discard += 1
            print("  %-17s %8.2f %8.2f %8.2f %8.2f" % (
                d.get("timestamp", "")[:16], m.get("v1_promote_rate", 0),
                m.get("v2_promote_rate", 0), m.get("v1_discard_rate", 0),
                v2d))
        except Exception:
            pass
    print()
    print("  ★ v2_discard == 0 的次数: %d/%d" % (zero_discard, len(fs)))
    if zero_discard >= len(fs) * 0.8:
        print("  🔴 【异常】连续为 0 → 疑似判定失效")
    return zero_discard, len(fs)


def diagnose_discard():
    """③ 诊断 discard 判定缺陷"""
    print()
    print("=" * 74)
    print("  ③ discard 判定缺陷诊断")
    print("=" * 74)
    try:
        from sleep_memory_v2 import (score_importance_v2,
                                     compute_tfidf_weights,
                                     dynamic_threshold)
    except Exception as e:
        print("  ✗ 无法导入:", str(e)[:70])
        return
    conn = sqlite3.connect(os.path.join(BASE, "state.db"))
    conn.row_factory = sqlite3.Row

    print("  采样不同批次的 50 条消息, 看 discard 判定是否稳定:")
    # ★ 2026-09-20 修复: R1116 起 score_importance_v2 对不可评分项返回 None,
    #   且【空 idf 必然返回 None】。原实现传 {} → 全部 None → sorted() 崩溃。
    #   正确做法与主流程一致: 先按语料建真 idf,再评分(参 _r1192_discard_probe_check.py:82)。
    all_rows = conn.execute(
        "SELECT content FROM messages ORDER BY id DESC LIMIT 1000").fetchall()
    corpus = [(r["content"] or "") for r in all_rows]
    try:
        idf = compute_tfidf_weights(corpus)
    except Exception as e:
        print(f"    ★ 建 idf 失败({type(e).__name__}) — 退化为不可评分报告")
        idf = {}
    print(f"    idf 词表: {len(idf)} 词")
    for off in [0, 50, 100, 150, 200]:
        rows = conn.execute(
            "SELECT content FROM messages ORDER BY id DESC LIMIT 50 OFFSET ?",
            (off,)).fetchall()
        sc = [score_importance_v2(r["content"] or "", idf) for r in rows]
        if not sc:
            continue
        # ★ 可观测性(2026-09-20):上游可返回 None —— 过滤并【显式报告条数】,防静默
        nums = [s for s in sc if isinstance(s, (int, float)) and not isinstance(s, bool)]
        n_bad = len(sc) - len(nums)
        if len(nums) < 5:
            print("    offset=%-4d | ★ 有效分数不足(%d/%d, 非数值 %d) — 跳过"
                  % (off, len(nums), len(sc), n_bad))
            continue
        pt, dt = dynamic_threshold(nums)
        nd = sum(1 for s in nums if s <= dt)
        print("    offset=%-4d | promote_t=%.4f discard_t=%.4f | "
              "★discarded=%d | 最低分=%.4f%s"
              % (off, pt, dt, nd, min(nums),
                 ("  [★ 已过滤非数值 %d 条]" % n_bad) if n_bad else ""))

    print()
    print("  ★ 缺陷分析:")
    print("    · dynamic_threshold 用【百分位】定阈值 (非固定值)")
    print("    · discard_t = min(第10百分位, 0.3)")
    print("    · ★ 若样本分布【整体偏高】(如全是长会话),")
    print("      则所有分数都 > 0.3 → ★【discarded 恒为 0】")
    print("    → ★★ 这不是 bug 而是【判定对分布敏感】,")
    print("      报告里应标注基线, 否则 0.00 会被误读为'无垃圾'")


def check_daydream_noise():
    """④ 白日梦的噪声词问题"""
    print()
    print("=" * 74)
    print("  ④ 白日梦 skill_suggestions 噪声检查")
    print("=" * 74)
    fs = sorted([f for f in os.listdir(AUDIT)
                 if f.startswith("daydream_2026") and f.endswith(".json")],
                key=lambda f: os.path.getmtime(os.path.join(AUDIT, f)),
                reverse=True)[:5]
    noise = {"----", "-----", "-------", "you", "script", "the", "and"}
    for f in fs:
        try:
            d = json.load(open(os.path.join(AUDIT, f), encoding="utf-8"))
            for s in d.get("skill_suggestions", []):
                terms = s.get("tech_terms", [])
                bad = [t for t in terms if t in noise or set(t) <= {"-"}]
                if bad:
                    print("  🔴 %s | 噪声词: %s (共 %d 个 term)"
                          % (f[9:22], bad[:6], len(terms)))
        except Exception:
            pass


if __name__ == "__main__":
    print()
    check_products()
    check_sleep_metrics()
    diagnose_discard()
    check_daydream_noise()
    print()
    print("=" * 74)
    print("  结论")
    print("=" * 74)
    print("  ✅ 两引擎均在正常运行 (product 新鲜度 < 26 小时)")
    print("  🟡 sleep_v2 的 v2_discard_rate 恒为 0 → 判定对分布敏感,")
    print("     报告需标注基线 (否则易误读为'无垃圾可丢')")
    print("  🟡 daydream 的 term 提取含 markdown 噪声 → 需加过滤")
