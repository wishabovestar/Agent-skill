# -*- coding: utf-8 -*-
"""睡眠/白日梦引擎健康检查 (四段式)

★ 用途: 用户问"检查 X 引擎运行情况和进展"时的标准第一步。
  四段输出覆盖本 skill Pitfall #24/#26/#27 全部判据。

★ 用法:
   python dream_engine_health.py [BASE]
   默认 BASE = D:/hermes/hermes-data/profiles/qqbot3

★ 四段:
   ① 产物新鲜度 (mtime < 26h 为健康)
   ② A/B 指标趋势 (★ 盯 v2_discard 是否恒为常数 = 判据失效信号)
   ③ discard 判定诊断 (采样不同批次, 看判定是否稳定)
   ④ daydream 噪声词检查 (tech_terms 含 markdown 符号/代词)

★ 判据要点:
   · 指标恒为 0 或恒定值 ≥3 期 → 先查判定链, 不要先解释为业务现象
   · v1 与 v2 都近全丢 → 业务正常; 仅 v2 恒 0 → 判据失效
"""
import json
import os
import sqlite3
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = sys.argv[1] if len(sys.argv) > 1 \
    else "D:/hermes/hermes-data/profiles/qqbot3"
AUDIT = os.path.join(BASE, "knowledge_base", "audit")
sys.path.insert(0, os.path.join(BASE, "scripts"))


def check_products():
    """① 产物新鲜度"""
    print("=" * 74)
    print("  ① 产物健康度")
    print("=" * 74)
    if not os.path.isdir(AUDIT):
        print("  ✗ audit 目录不存在:", AUDIT)
        return
    for pfx in ["daydream_", "sleep_v2_", "daydream_v3_", "sleep_"]:
        fs = [f for f in os.listdir(AUDIT)
              if f.startswith(pfx) and f.endswith(".json")]
        fs.sort(key=lambda f: os.path.getmtime(os.path.join(AUDIT, f)),
                reverse=True)
        if fs:
            p = os.path.join(AUDIT, fs[0])
            age_h = (datetime.now().timestamp() - os.path.getmtime(p)) / 3600
            flag = "✅" if age_h < 26 else "🔴"
            print("  %s %-14s %3d 个 | 最新 %s (%.1f 小时前)"
                  % (flag, pfx, len(fs), fs[0][:34], age_h))


def check_sleep_metrics(n=8):
    """② A/B 指标趋势 — ★ 盯恒为常数的信号"""
    print()
    print("=" * 74)
    print("  ② 睡眠引擎 A/B 指标 (最近 %d 次)" % n)
    print("=" * 74)
    if not os.path.isdir(AUDIT):
        return 0, 0
    fs = sorted([f for f in os.listdir(AUDIT)
                 if f.startswith("sleep_v2_") and f.endswith(".json")],
                key=lambda f: os.path.getmtime(os.path.join(AUDIT, f)),
                reverse=True)[:n]
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
    if fs and zero_discard >= len(fs) * 0.8:
        print("  🔴 【异常】连续为 0 → 疑似判定失效 (见 Pitfall #24)")
        print("     判据: v1 与 v2 都近全丢 = 业务正常; 仅 v2 恒 0 = 判据失效")
    return zero_discard, len(fs)


def diagnose_discard():
    """③ discard 判定缺陷诊断 (采样不同批次看稳定性)"""
    print()
    print("=" * 74)
    print("  ③ discard 判定缺陷诊断")
    print("=" * 74)
    try:
        from sleep_memory_v2 import (score_importance_v2,
                                     compute_tfidf_weights,
                                     dynamic_threshold)
    except Exception as e:
        print("  ✗ 无法导入 sleep_memory_v2:", str(e)[:70])
        return
    db = os.path.join(BASE, "state.db")
    if not os.path.exists(db):
        print("  ✗ state.db 不存在:", db)
        return
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    print("  采样不同批次的 50 条消息, 看 discard 判定是否稳定:")
    for off in [0, 50, 100, 150, 200]:
        rows = conn.execute(
            "SELECT content FROM messages ORDER BY id DESC LIMIT 50 OFFSET ?",
            (off,)).fetchall()
        sc = [score_importance_v2(r["content"] or "", {}) for r in rows]
        sc = [x for x in sc if x is not None]
        if not sc:
            print("    offset=%-4d | (全为不可评分条目)" % off)
            continue
        pt, dt = dynamic_threshold(sc)
        nd = sum(1 for s in sc if s <= dt)
        print("    offset=%-4d | promote_t=%.4f discard_t=%.4f | "
              "discarded=%d | 最低分=%.4f | 不同值数=%d"
              % (off, pt, dt, nd, min(sc), len(set(round(x, 6) for x in sc))))
    print()
    print("  ★ 缺陷模式: 分布塌缩成单一值 → 该值成为阈值 → 判定失效")
    print("    (哨兵值 0.05 是典型; 修法 = 返回 None 由调用方过滤, 见 Pitfall #26)")


def check_noise():
    """④ daydream 噪声词检查"""
    print()
    print("=" * 74)
    print("  ④ 白日梦 skill_suggestions 噪声检查")
    print("=" * 74)
    if not os.path.isdir(AUDIT):
        return
    fs = sorted([f for f in os.listdir(AUDIT)
                 if f.startswith("daydream_2026") and f.endswith(".json")],
                key=lambda f: os.path.getmtime(os.path.join(AUDIT, f)),
                reverse=True)[:5]
    noise = {"----", "-----", "-------", "you", "script", "the", "and"}
    hit = 0
    for f in fs:
        try:
            d = json.load(open(os.path.join(AUDIT, f), encoding="utf-8"))
            for s in d.get("skill_suggestions", []):
                terms = s.get("tech_terms", [])
                bad = [t for t in terms if t in noise or set(t) <= {"-"}]
                if bad:
                    hit += 1
                    print("  🔴 %s | 噪声词: %s" % (f[9:22], bad[:6]))
        except Exception:
            pass
    if hit == 0:
        print("  ✅ 未检出噪声词 (最近 5 份)")


if __name__ == "__main__":
    print()
    check_products()
    check_sleep_metrics()
    diagnose_discard()
    check_noise()
    print()
    print("=" * 74)
    print("  判据速查")
    print("=" * 74)
    print("  ✅ 产物 mtime < 26h  → 引擎在跑")
    print("  🔴 指标恒为 0/常数 ≥3 期 → 先查判定链, 不是业务现象 (Pitfall #24)")
    print("  🔴 v1/v2 不对称 (仅 v2 恒 0) → 判据失效 (v1 与 v2 都近全丢 = 业务正常)")
    print("  🔴 分布塌缩为单一值 → 哨兵值污染 (Pitfall #26, 改用 None)")
