#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_index_coverage.py — 核对 knowledge_base 的【检索可达性】覆盖率

【为什么存在】
  R1125 (2026-09-16) 实测: hermes_index.py 的 index_kb() 曾只扫 **/*.md,
  而巡天采集的知识是 .json ⇒ docs 表里 source='kb-xuntian' = 0
  ⇒ 「巡天采集的全部知识从未可检索」。

★★★ 2026-09-17 修正一个【本脚本自己的】判据缺陷 (第 9 次"测试错觉"):
    索引 docs.path 存的是 **Windows 反斜杠** 路径, 而首版用正斜杠做
    `LIKE '%knowledge_base/vision/%'` ⇒ **永远 0 命中** ⇒ 假报"域知识全部未索引"。
  ⇒ 教训: **比对路径前先确认存储侧的路径分隔符**, 不能想当然。
    现在的做法: 从 DOS 表实际取样例路径推断分隔符, 再构造 LIKE。

【判据】
  磁盘 (md+json) vs 索引内条目数, 按域聚合。
  另按 basename 精确核算【哪些文件真的没进索引】—— 这是最可靠的判据。
"""
import os
import sqlite3
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = r"D:\hermes\hermes-data\profiles\qqbot3"
INDEX = os.path.join(ROOT, "scripts", "hermes_index.db")
KB = os.path.join(ROOT, "knowledge_base")

# 不该进知识索引的机器状态文件 (检索无意义, 索引它们只会稀释召回)
STATE_NAMES = {
    "registry.json", "metrics.json", "exp_pool.json", "route_cache.json",
    "github_feedback_state.json", "blocked_board.json", "agent_sessions.json",
    "optimal_params.json", "optimized_params.json", "plans.json",
    "research_queue.json", "review_pane.json", "basert_models.json",
}


def main():
    c = sqlite3.connect(INDEX)
    cur = c.cursor()

    # ── 0) 推断存储侧分隔符 (不假设)
    cur.execute("SELECT path FROM docs LIMIT 1")
    sample = (cur.fetchone() or [""])[0]
    sep = "\\" if "\\" in sample else "/"
    print("索引存储侧路径分隔符: %r  (样例: %s)" % (sep, sample[:80]))
    print()

    # ── 1) 磁盘实数
    disk = {}
    for r, _d, fs in os.walk(KB):
        for f in fs:
            ext = os.path.splitext(f)[1].lower()
            if ext in (".md", ".json"):
                disk[os.path.normcase(os.path.join(r, f))] = ext
    md = sum(1 for v in disk.values() if v == ".md")
    js = sum(1 for v in disk.values() if v == ".json")
    print("磁盘 knowledge_base:  .md %d | .json %d | 合计 %d" % (md, js, md + js))

    # ── 2) 索引内 basename 集合 (最可靠判据)
    cur.execute("SELECT path, source FROM docs")
    idx_pairs = cur.fetchall()
    idx_base = {}
    for p, s in idx_pairs:
        if p:
            idx_base[os.path.basename(os.path.normcase(p))] = s
    cur.execute("SELECT source, COUNT(*) FROM docs GROUP BY source ORDER BY 2 DESC")
    print("索引 docs 总数: %d" % len(idx_pairs))
    print("docs 按 source:")
    for s, n in cur.fetchall():
        print("    %-22s %6d" % (str(s)[:22], n))
    print()

    # ── 3) 按域核对
    print("%-16s %6s %6s %6s  %s" % ("域", "磁盘", "索引", "缺失", "判定"))
    t_d = t_i = t_m = 0
    dom_rows = []
    domains = Counter()
    for p, ext in disk.items():
        rel = os.path.relpath(p, os.path.normcase(KB))
        d = rel.split(os.sep)[0] if os.sep in rel else "(顶层)"
        domains[d] += 1
    for d, cnt in sorted(domains.items(), key=lambda x: -x[1]):
        if cnt < 5:
            continue
        files = [p for p in disk
                 if (os.path.relpath(p, os.path.normcase(KB)).split(os.sep)[0]
                     if os.sep in os.path.relpath(p, os.path.normcase(KB)) else "(顶层)") == d]
        inn = sum(1 for p in files if os.path.basename(p) in idx_base)
        miss = cnt - inn
        mark = "✅" if miss == 0 else ("🟡" if inn > 0 else "🔴")
        t_d += cnt
        t_i += inn
        t_m += miss
        dom_rows.append((d, cnt, inn, miss, mark))
        print("%-16s %6d %6d %6d  %s" % (d[:16], cnt, inn, miss, mark))
    print()
    print("合计(≥5 文件的域): 磁盘 %d | 索引 %d | 缺失 %d | 覆盖率 %.1f%%"
          % (t_d, t_i, t_m, 100.0 * t_i / max(1, t_d)))
    print()

    # ── 4) 缺失清单分类
    missing = [p for p in disk if os.path.basename(p) not in idx_base]
    state = [p for p in missing if os.path.basename(p).lower() in STATE_NAMES]
    kn = [p for p in missing if os.path.basename(p) not in STATE_NAMES]
    print("★ 未入索引 %d 个:" % len(missing))
    print("   机器状态文件(不该索引): %d" % len(state))
    print("   其他(★ 潜在地检索不到): %d" % len(kn))
    if kn:
        # 按目录聚合
        dc = Counter()
        for p in kn:
            rel = os.path.relpath(p, os.path.normcase(KB))
            dc[rel.split(os.sep)[0] if os.sep in rel else "(顶层)"] += 1
        print("   按一级目录:")
        for d, n in dc.most_common(14):
            print("     %-26s %5d" % (d[:26], n))
        print("   示例:")
        for p in kn[:6]:
            print("     " + os.path.relpath(p, os.path.normcase(KB)))

    # ── 5) R1125 核心判据
    cur.execute("SELECT COUNT(*) FROM docs WHERE source='kb-xuntian'")
    nx = cur.fetchone()[0]
    print()
    print(("✅ R1125 核心判据: source='kb-xuntian' = %d (修复前为 0)" % nx) if nx
          else "🔴 R1125 核心判据: source='kb-xuntian' = 0")
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
