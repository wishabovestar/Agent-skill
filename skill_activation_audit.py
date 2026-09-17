#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skill_activation_audit.py — 技能【激活率】埋点 (补本机可观测性盲区)

【缺口来源】
  《深入理解 AI Agent》§9.3 表9-3 四指标中, 本机【完全未测】的两项:
    ① 产物激活率 — 技能是否在【正确场景】被加载
    ② 遵循成功率 — 加载后是否真被遵循
  本机此前只有"cron 是否执行"这一层可观测性 (R1133)。

【扫描面 (★ 三条路径全查, 单一来源会严重低估)】
  数据源: <HOME>/state.db 的 messages 表
    ① content    列: 正文/工具结果里的 skill_view 与 skills/x/SKILL.md 路径
    ② tool_calls 列: ★ 关键 —— 工具调用参数在【这一列】, 不在 content
       实测本机: tool_calls 非空 93,721 行; 含 SKILL.md 者 2,738 行;
                 content 含 SKILL.md 者 5,419 行
  匹配: skill_view(name='x') | 任意路径中的 skills/<...>/x/SKILL.md

【输出】
  · 激活 / 从未激活 计数 + 激活次数桶分布 (决策分布画像: 断言"不是 0 也不是全部")
  · Top 高频 / 从未激活清单 (漂移候选, 供 skill-library-governance 判定)

【★ 诚实边界 (写死在输出)】
  · 测的是【激活率】(被加载), **不是遵循成功率** —— 后者需读加载后的行为, 未实现。
  · 覆盖 3 条路径后仍可能有其它加载路径 ⇒ 计数是【下界】, 不能说"从未被用过"。
  · 正文提及属弱证据, 单独存放, 不并入主计数。

用法: python skill_activation_audit.py [--days 30] [--json]
"""
# side_effects: [--json 时写 data/skill_activation.json]

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(HOME, "state.db")
SK = os.path.join(HOME, "skills")

# skill_view(name='x')
RX_VIEW = re.compile(r"""skill_view\s*\(\s*name\s*=\s*['"]([A-Za-z0-9_\-]{3,})['"]""")
# 任意路径里的 skills/<...>/x/SKILL.md  (正/反斜杠都吃)
RX_PATH = re.compile(r"""skills[\\/](?:[A-Za-z0-9_\-]+[\\/])*([A-Za-z0-9_\-]{3,})[\\/]SKILL\.md""")


def live_skills():
    names = set()
    for root, dirs, files in os.walk(SK):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if "SKILL.md" in files:
            names.add(os.path.basename(root))
    return names


def scan(days):
    """★ 失败【向上抛】, 绝不静默返回 0

    首版教训 (2026-09-16): 列名猜成 `created_at`(实际是 `timestamp`) ⇒ 查询抛异常 ⇒
    被 except 吞掉并返回 0 ⇒ 输出"195 个技能全部从未激活"的【假结论】。
    静默失败与"真的没有"在输出上不可区分, 是教科书级失效。
    """
    if not os.path.exists(STATE):
        raise FileNotFoundError("state.db 不存在: %s" % STATE)
    c = sqlite3.connect(STATE)
    cols = [r[1] for r in c.execute("PRAGMA table_info(messages)")]
    tcol = next((x for x in ("timestamp", "created_at", "ts", "time") if x in cols), None)
    if tcol is None:
        raise RuntimeError("messages 表无时间列 (已有: %s)" % ", ".join(cols[:12]))
    if "content" not in cols:
        raise RuntimeError("messages 表无 content 列")
    has_tc = "tool_calls" in cols

    since = (datetime.now() - timedelta(days=days)).timestamp() if days else 0
    where = "content is not null" + (" or tool_calls is not null" if has_tc else "")
    sel = "content, %s%s" % (tcol, ", tool_calls" if has_tc else "")
    strong, weak, n_content, n_tool = Counter(), Counter(), 0, 0

    for row in c.execute("select %s from messages where %s" % (sel, where)):
        content = row[0] if isinstance(row[0], str) else ""
        ts = row[1]
        tc = row[2] if (has_tc and len(row) > 2 and isinstance(row[2], str)) else ""
        if since and ts is not None:
            try:
                if float(ts) < since:
                    continue
            except (TypeError, ValueError):
                pass                      # 时间列非数值 ⇒ 不做时间过滤, 而非静默丢行
        if content:
            n_content += 1
        if tc:
            n_tool += 1
        for blob in (content, tc):
            if not blob:
                continue
            for m in RX_VIEW.finditer(blob):
                strong[m.group(1)] += 1
            for m in RX_PATH.finditer(blob):
                strong[m.group(1)] += 1
        # 弱证据: 正文里出现形如 name='x' 的键值 (≥3 字符, 滤掉占位名)
        for m in re.finditer(r"""["']?name["']?\s*[:=]\s*['"]([A-Za-z0-9_\-]{3,})['"]""", content):
            weak[m.group(1)] += 1

    if n_content == 0 and n_tool == 0:
        raise RuntimeError("扫描到 0 条消息 —— 查询/过滤可疑, 不静默放行")
    return strong, weak, n_content, n_tool


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    live = live_skills()
    try:
        strong, weak, n_c, n_t = scan(a.days)
    except Exception as e:
        print("🔴 **技能激活审计失败** (%s)" % type(e).__name__)
        print("   %s" % str(e)[:300])
        print("   ★ 按纪律: 失败向上报, 不返回 0 —— 「0 命中」与「查询坏了」必须可区分。")
        return 2

    act = Counter({k: v for k, v in strong.items() if k in live})
    unknown = Counter({k: v for k, v in strong.items() if k not in live})
    never = sorted(live - set(act))

    print("═" * 78)
    print("  技能激活审计 | 近 %d 天" % a.days)
    print("═" * 78)
    print("  扫描: content %s 条 | tool_calls %s 条" % (format(n_c, ","), format(n_t, ",")))
    print("  技能总数: %d" % len(live))
    print("  🟢 有激活记录: %d (%.1f%%)" % (len(act), 100.0 * len(act) / max(1, len(live))))
    print("  🔴 从未激活: %d (%.1f%%)" % (len(never), 100.0 * len(never) / max(1, len(live))))
    if unknown:
        print("  ⚠️ 痕迹里的未知名字(已删/改名/误匹配): %d — %s"
              % (len(unknown), ", ".join(list(unknown)[:6])))

    vals = sorted(act.values(), reverse=True)
    print()
    print("  ── 激活次数分布 (决策分布画像: 断言「不是 0 也不是全部」) ──")
    if vals:
        print("     总激活 %d | 活跃技能 %d | 最高 %d | 中位 %d"
              % (sum(vals), len(vals), vals[0], vals[len(vals) // 2]))
        for lo, hi in ((1, 2), (3, 10), (11, 50), (51, 10 ** 9)):
            k = sum(1 for v in vals if lo <= v <= hi)
            lab = "%d-%d" % (lo, hi) if hi < 10 ** 9 else ">%d" % lo
            print("     %-9s %3d 个  %s" % (lab, k, "█" * min(40, k)))
    print()
    print("  ── Top15 高频 ──")
    for k, v in act.most_common(15):
        print("     %-42s %d" % (k, v))
    print()
    print("  ── 从未激活 (漂移候选, 前 18) ──")
    for k in never[:18]:
        print("     %s" % k)
    if len(never) > 18:
        print("     …还有 %d 个" % (len(never) - 18))
    print()
    print("  ★ 诚实边界: 测的是【激活率】(是否被加载), **不是遵循成功率**。")
    print("    已覆盖 skill_view / SKILL.md 路径 / tool_calls 三类痕迹, 仍有漏计 ⇒ 计数是【下界】。")

    if a.json:
        out = os.path.join(HOME, "data", "skill_activation.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"days": a.days, "scanned_content": n_c, "scanned_toolcalls": n_t,
                       "skills_total": len(live), "activated": len(act),
                       "never_activated": never, "counts": dict(act.most_common()),
                       "weak_mentions": dict(weak.most_common(50))},
                      f, ensure_ascii=False, indent=2)
        print("\n  ✅ 已存: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
