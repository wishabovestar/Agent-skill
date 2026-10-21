# -*- coding: utf-8 -*-
"""仓库规模可靠统计 (R1106)

★ 教训: shell 的 `find -exec wc -l` 或 `wc -l $(files)` 在文件数多时
   会因【命令行参数超限】(WinError 206 / Argument list too long)
   静默丢失文件 → 得到【远小于真实值】的假数字!

★ 实测对比 (oddorder 仓库):
   · find -exec wc -l  → 127,543 行  (假!)
   · wc -l 全量        → WinError 206
   · Python 逐行       → 【845,517 行】(真)
   差异: 6.6 倍!

★ 本脚本用 Python os.walk + 逐行读, 统计可靠。
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def measure(root, exts=(".lean", ".v")):
    """可靠统计: 返回 (文件数, 行数, 按顶层目录分解)"""
    n = 0
    total = 0
    bydir = {}
    for r, dirs, files in os.walk(root):
        if ".git" in r.split(os.sep):
            continue
        for f in files:
            if not f.endswith(exts):
                continue
            p = os.path.join(r, f)
            try:
                with open(p, "rb") as fh:
                    L = sum(1 for _ in fh)
            except Exception:
                continue
            n += 1
            total += L
            rel = os.path.relpath(r, root)
            top = rel.split(os.sep)[0] if rel != "." else "(root)"
            bydir[top] = bydir.get(top, 0) + L
    return n, total, bydir


def main():
    repos = [
        (r"C:\Users\Administrator\oddorder", ".lean", "奇数阶 (Lean 端口)"),
        (r"C:\Users\Administrator\lean-liquid", ".lean", "LTE (Liquid Tensor)"),
        (r"C:\Users\Administrator\fourcolor", ".v", "四色定理 (Coq/Rocq)"),
        (r"C:\Users\Administrator\prove2me_research\fermats-last-theorem", ".lean",
         "FLT (Anthropic/Prove2Me)"),
    ]
    print("=" * 74)
    print("  仓库规模可靠统计 (R1106) — Python 逐行, 无参数限制")
    print("=" * 74)
    results = []
    for path, ext, name in repos:
        if not os.path.isdir(path):
            print("\n  %s: (未 clone)" % name)
            continue
        n, tot, bydir = measure(path, (ext,))
        results.append((name, n, tot))
        print("\n  ★ %s" % name)
        print("     路径: %s" % path)
        print("     %s 文件: %d | 行数: %d" % (ext, n, tot))
        if bydir:
            print("     按顶层目录 (前 6):")
            for k, v in sorted(bydir.items(), key=lambda x: -x[1])[:6]:
                print("       %-28s %8d 行" % (k[:28], v))

    print()
    print("=" * 74)
    print("  汇总")
    print("=" * 74)
    for name, n, tot in sorted(results, key=lambda x: -x[2]):
        print("  %-28s %6d 文件 | %9d 行" % (name, n, tot))


if __name__ == "__main__":
    main()
