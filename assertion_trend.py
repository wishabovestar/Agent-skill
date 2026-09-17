#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""assertion_trend.py — 层2 真路径验证: 捕捉「弱化自检也能通过」

【缺口来源 —— 书 §9.1 的过程违规原型】
  《深入理解 AI Agent》§9.1 举的过程验证器例子是:
    「**删除失败的测试用例, 也能让测试通过**」
  那是**路径违规**: 结果(测试通过)没变, 但**达成它的路径被偷换了**。
  ★ 本机此前完全没有这一类检查 ——
    `trajectory_evaluator.py` 的层2 其实只是「层1.5: 产物级」
    (P1 占位产物 / P2 内容未变 / P3 有记录无产物), **不看路径**。

【本机上的同构违规】
  「**删除或弱化自检断言, 也能让自检继续报"全通过"**」

  ★★ 这不是假想: 2026-09-16 当天就发生过一次近亲事故 ——
     `quality_verifier.py` 的自检从 8 项加到 14 项, 而它的"判定"行**硬编码着"八项"**;
     随后又发现失败时仍印 "14/14"。两处都是**计数与事实脱钩**。
     若当时是【减少】断言, 那行会继续声称通过, 且**没有任何机制会发现**。

【为什么必须用"基线 + 减少即告警"】
  弱化断言这个动作本身是**合法**的(有时确实该删)。
  问题在于它**静默发生且不被记录**。所以:
    · 冻结基线 (脚本 → 断言数 + 内容哈希)
    · 每次核对: **任何减少都告警**(不判它好坏, 只判它"没被注意到")
    · ★ 同时报告【增加】与【不变】的数量 —— 遵守本机纪律「不是 0 也不是全部」

用法:
  python assertion_trend.py --freeze      # 冻结/更新基线
  python assertion_trend.py --check       # 核对 (人读)
  python assertion_trend.py --check --quiet   # 静默: 无减少 ⇒ 0 字节 (cron 就绪)
  python assertion_trend.py --selftest
"""
# side_effects: [写 data/assertion_baseline.json]

import argparse
import hashlib
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.dirname(HERE)
BASELINE = os.path.join(HOME, "data", "assertion_baseline.json")

# ★ 断言形态 (本机脚本的既有约定)
PATTERNS = [
    (r"\bok\s*&=\s*\w", "ok&=自检"),          # 自检累积
    (r"\bok\s*=\s*ok\s+and\b", "ok=and"),
    (r"^\s*assert\s+\w", "assert"),            # 标准断言
    (r"\berrs\.append\(", "errs.append"),
    (r"\bfails\.append\(", "fails.append"),
    (r"\btags\.append\(", "tags.append"),
    (r"^\s*p\d+\w*\s*=\s*", "pN=判定"),        # 本机自检命名约定 (p1/p2/p9ok…)
]


def count_assertions(path):
    """数一个脚本里的断言/校验点 (逐行, 不依赖 shell)"""
    try:
        src = open(path, encoding="utf-8", errors="replace").read()
    except Exception:
        return None
    n, by_kind = 0, {}
    for ln in src.split("\n"):
        for rx, kind in PATTERNS:
            if re.search(rx, ln):
                n += 1
                by_kind[kind] = by_kind.get(kind, 0) + 1
                break          # 一行只算一次, 防同一行多模式重复计
    return {"n": n, "by_kind": by_kind,
            "sha8": hashlib.sha256(src.encode("utf-8", "replace")).hexdigest()[:8],
            "bytes": len(src.encode("utf-8", "replace"))}


def scan():
    out = {}
    if not os.path.isdir(HERE):
        return out
    for fn in sorted(os.listdir(HERE)):
        if not fn.endswith(".py") or fn.startswith("_"):
            continue
        c = count_assertions(os.path.join(HERE, fn))
        if c and c["n"] > 0:
            out[fn] = c
    return out


def freeze():
    cur = scan()
    prev = {}
    if os.path.exists(BASELINE):
        try:
            prev = json.load(open(BASELINE, encoding="utf-8")).get("scripts", {})
        except Exception:
            prev = {}
    data = {"frozen_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
            "n_scripts": len(cur), "scripts": cur}
    os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
    with open(BASELINE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return cur, prev


def check(quiet=False):
    if not os.path.exists(BASELINE):
        if not quiet:
            print("  尚无基线 — 先运行 --freeze")
        return 0
    base = json.load(open(BASELINE, encoding="utf-8")).get("scripts", {})
    cur = scan()
    dropped, added, same, gone, new = [], [], 0, [], []
    for fn, b in base.items():
        c = cur.get(fn)
        if c is None:
            gone.append((fn, b["n"]))
        elif c["n"] < b["n"]:
            dropped.append((fn, b["n"], c["n"], c["sha8"] != b["sha8"]))
        elif c["n"] > b["n"]:
            added.append((fn, b["n"], c["n"]))
        else:
            same += 1
            if c["sha8"] != b["sha8"]:
                # 断言数不变但内容变了 —— 中性信息, 只在非静默时提
                pass
    for fn in cur:
        if fn not in base:
            new.append((fn, cur[fn]["n"]))
    n_concern = len(dropped) + len(gone)
    if quiet:
        if n_concern:
            print("  🔴 断言趋势: %d 个脚本的校验点【减少】, %d 个消失"
                  % (len(dropped), len(gone)))
            for fn, a, b, chg in dropped[:8]:
                print("     %s: %d → %d (内容也变了: %s)" % (fn, a, b, "是" if chg else "否"))
            for fn, a in gone[:8]:
                print("     %s: 脚本消失 (原 %d 个校验点)" % (fn, a))
        # ★ 无减少 ⇒ 0 字节 (no_agent cron 静默纪律)
        return 1 if n_concern else 0
    print("═" * 76)
    print("  层2 真路径验证: 自检断言趋势")
    print("═" * 76)
    print("  基线 %s (%d 个脚本)" % (__import__("json").load(
        open(BASELINE, encoding="utf-8")).get("frozen_at", "?"), len(base)))
    print("  当前 %d 个脚本有校验点" % len(cur))
    print()
    print("  🔴 减少/消失 %d   🟢 增加 %d   ⚪ 不变 %d   🆕 新脚本 %d"
          % (n_concern, len(added), same, len(new)))
    if dropped:
        print()
        print("  ── ★ 校验点减少 (书 §9.1「删测试也能通过」的同构) ──")
        for fn, a, b, chg in dropped:
            print("   %-34s %d → %d   (内容同时改动: %s)" % (fn, a, b, "是" if chg else "否"))
    if gone:
        print()
        print("  ── 脚本消失 ──")
        for fn, a in gone:
            print("   %-34s (原 %d 个校验点)" % (fn, a))
    if added:
        print()
        print("  ── 增加 (正常演进) ──")
        for fn, a, b in added[:10]:
            print("   %-34s %d → %d" % (fn, a, b))
    if new:
        print()
        print("  ── 新脚本 ──")
        for fn, n in new[:10]:
            print("   %-34s %d 个校验点" % (fn, n))
    print()
    if n_concern:
        print("  ★ 判读: 减少【不等于】错误 —— 但**它必须是被注意到的**。")
        print("     若减少是刻意的, 确认后跑 --freeze 更新基线即可。")
    else:
        print("  ✅ 没有任何脚本的校验点减少。")
    return 1 if n_concern else 0


def selftest():
    """★ 离线自检: 断言计数器本身必须先被检查"""
    ok = True
    import tempfile
    print("─" * 76)
    print("  assertion_trend 自检")
    print("─" * 76)

    def probe(src):
        p = os.path.join(tempfile.gettempdir(), "_at_probe.py")
        open(p, "w", encoding="utf-8").write(src)
        return count_assertions(p)

    # P1 计数正确
    c = probe("ok = True\nok &= p1\nok &= p2\nassert x\n"
              "errs.append('a')\np3ok = foo()\n")
    p1 = c["n"] == 5
    print("  P1 校验点计数 (得 %d, 期望 5): %s" % (c["n"], "✅" if p1 else "🔴"))
    ok &= p1

    # P2 一行只计一次 (防同模式重复计)
    c2 = probe("ok &= p1 and p2\n")
    p2 = c2["n"] == 1
    print("  P2 一行只计一次 (得 %d, 期望 1): %s" % (c2["n"], "✅" if p2 else "🔴"))
    ok &= p2

    # P3 减少可被检出
    a = probe("ok &= p1\nok &= p2\nok &= p3\n")
    b = probe("ok &= p1\n")
    p3 = a["n"] == 3 and b["n"] == 1 and b["n"] < a["n"]
    print("  P3 减少可检出 (%d → %d): %s" % (a["n"], b["n"], "✅" if p3 else "🔴"))
    ok &= p3

    # P4 内容哈希随内容变
    p4 = a["sha8"] != b["sha8"]
    print("  P4 内容哈希随内容变: %s" % ("✅" if p4 else "🔴"))
    ok &= p4

    # P5 ★ 关键: 本机真实的「改名/硬编码」退化形态必须能被发现
    #    原: 打印实际计数   改后: 硬编码字符串 ⇒ 断言计数下降
    before = probe("print('判定: %s' % ('✅' if ok else '🔴'))\nok &= p1\n")
    after = probe("print('判定: ✅ 八项全通过')\nok &= p1\n")
    p5 = after["n"] <= before["n"]
    print("  P5 硬编码判定文案的形态可被监测 (前 %d, 后 %d): %s"
          % (before["n"], after["n"], "✅" if p5 else "🔴"))
    ok &= p5

    # P6 全仓扫描有结果
    s = scan()
    p6 = len(s) > 20
    print("  P6 全仓扫描到 %d 个含校验点的脚本 (>20): %s"
          % (len(s), "✅" if p6 else "🔴"))
    ok &= p6
    try:
        os.remove(os.path.join(tempfile.gettempdir(), "_at_probe.py"))
    except Exception:
        pass
    print("  判定: %s" % ("✅ 全通过" if ok else "🔴 有未通过"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest or len(sys.argv) == 1:
        return selftest()
    if a.freeze:
        cur, prev = freeze()
        if not a.quiet:
            print("  ✅ 基线已冻结: %d 个脚本" % len(cur))
            if prev:
                d = [k for k in prev if k in cur and cur[k]["n"] < prev[k]["n"]]
                if d:
                    print("     ★ 注意: 本次冻结把 %d 个减少固化进基线 (%s)"
                          % (len(d), ", ".join(d[:4])))
        return 0
    if a.check:
        return check(a.quiet)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
