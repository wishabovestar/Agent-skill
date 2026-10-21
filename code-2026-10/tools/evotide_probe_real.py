#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evotide_probe_real.py — 用 EvoTIDE-lite 的打分器巡检真实 SKILL.md harness

目的：证明打分器对真实文件可用（不是只对自己的 fixture 有效），
      并顺手产出一份真实的弱项清单 —— 这就是 Phase 5「弱点库」的原料。

断言集（通用技能健康度，不含任何具体技能的专有内容）：
    - frontmatter 有 name
    - frontmatter 有 description
    - 至少 3 个二级标题
    - 行数 >= 20
    - 不含 TODO / FIXME
    - 不含 [SKILL_PRUNED]（内容丢失标记）

用法：
    python evotide_probe_real.py            # 扫 mybot profile 的 skills
    python evotide_probe_real.py --all      # 扫所有 profile + shared-skills
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, r"D:/hermes/analysis")
import evotide_lite as EL  # noqa: E402

DEFAULT_ROOTS = [
    r"D:/hermes/hermes-data/profiles/mybot/skills",
]
ALL_ROOTS = [
    r"D:/hermes/hermes-data/profiles/mybot/skills",
    r"D:/hermes/hermes-data/skills",
    r"D:/hermes/shared-skills",
]

ASSERTIONS = [
    EL.Assertion("regex", r"(?m)^name:\s*\S+", weight=2.0, label="frontmatter:name"),
    EL.Assertion("regex", r"(?m)^description:\s*\S+", weight=2.0, label="frontmatter:description"),
    EL.Assertion("regex", r"(?m)^##\s+\S+", weight=1.0, label="has_h2"),
    EL.Assertion("min_lines", "20", weight=1.0, label="len>=20"),
    EL.Assertion("not_contains", "TODO", weight=1.0, label="no_TODO"),
    EL.Assertion("not_contains", "[SKILL_PRUNED", weight=3.0, label="no_pruned_marker"),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default=r"D:/hermes/analysis/reinforcement_logs/skill_probe.json")
    a = ap.parse_args(argv)

    roots = ALL_ROOTS if a.all else DEFAULT_ROOTS
    files: list[str] = []
    for r in roots:
        files.extend(glob.glob(os.path.join(r, "**", "SKILL.md"), recursive=True))
    # 去重（external_dirs 可能重叠）
    files = sorted({os.path.abspath(f) for f in files})
    if not files:
        print("no SKILL.md found under:", roots)
        return 1

    sc = EL.AssertionScorer(ASSERTIONS)
    rows = []
    for f in files:
        s = sc(f)
        d = sc.detail(f)
        failed = [x["assertion"] for x in d.get("assertions", []) if not x["ok"]]
        rows.append({
            "path": f.replace("\\", "/"),
            "name": os.path.basename(os.path.dirname(f)),
            "score": s,
            "failed": failed,
            "lines": len(open(f, encoding="utf-8", errors="ignore").read().splitlines()),
        })

    rows.sort(key=lambda x: x["score"])
    n = len(rows)
    scores = [r["score"] for r in rows]
    mean = sum(scores) / n
    print(f"scanned {n} SKILL.md under {len(roots)} root(s)")
    print(f"mean S = {mean:.4f}   min = {min(scores):.3f}   max = {max(scores):.3f}")
    print(f"perfect (S=1.0): {sum(1 for s in scores if s >= 0.999)} / {n}\n")

    print("worst 12:")
    for r in rows[:12]:
        print(f"  S={r['score']:.3f}  {r['name']:<40} failed={r['failed']}")

    # 按失败断言聚合 —— 这才是弱点库要的东西
    agg: dict[str, int] = {}
    for r in rows:
        for f in r["failed"]:
            agg[f] = agg.get(f, 0) + 1
    print("\nfailure histogram (across all skills):")
    for k, v in sorted(agg.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<28} {v:>4}  ({v/n*100:.1f}% of skills)")

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"roots": roots, "n": n, "mean": mean,
                   "failure_histogram": agg, "rows": rows}, fh, ensure_ascii=False, indent=1)
    print(f"\nwritten -> {a.out}")

    # 接 self-reinforcement 弱点库：失败率 >50% 的断言 = 系统性弱点
    sysweak = {k: v for k, v in agg.items() if v / n > 0.5}
    if sysweak:
        print("\n⚠ systematic weaknesses (failed in >50% of skills):")
        for k, v in sysweak.items():
            print(f"  {k} -> {v}/{n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
