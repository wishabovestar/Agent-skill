# -*- coding: utf-8 -*-
"""档案编号查重与分配 (R1003 修复 — 今日暴露的编号冲突)

问题 (今日实测): 两批并行子代理各自用 r993/r994 起编号 → 【撞车】
  · r994_anthropic_new5 (95.8KB) vs r994_trending_security (26KB)
  · r995_anthropic_new4 (57KB)  vs r995_trending_batch (5.5KB)
  根因: 子代理任务书未指定【唯一起始编号】, 各自独立选取

本工具:
  ① check  — 扫描知识库, 列出重复编号 (含历史遗留)
  ② next   — 返回当前最大编号 + 1 (供任务书预先分配)
  ③ reserve N — 预留连续 N 个编号 (打印给并行子代理分配)

用法:
  python research_rid.py --check
  python research_rid.py --next
  python research_rid.py --next 4
"""
# side_effects: [无写入, 只读]
import os, re, sys, io, glob
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
KB = r"<PROFILE_ROOT>\knowledge_base"
RID_RE = re.compile(r"^(r)(\d+)([a-z]?)_", re.I)


def scan_rids(base=KB):
    """返回 {编号: [文件路径...]}"""
    m = defaultdict(list)
    for f in glob.glob(os.path.join(base, "**", "*.md"), recursive=True):
        name = os.path.basename(f)
        mo = RID_RE.match(name)
        if mo:
            key = f"{mo.group(1).lower()}{mo.group(2)}{mo.group(3)}"
            m[key].append(os.path.relpath(f, base))
    return m


def check(verbose=False):
    m = scan_rids()
    dups = {k: v for k, v in m.items() if len(v) > 1}
    print(f"=== 编号查重 (共 {len(m)} 个编号, {sum(len(v) for v in m.values())} 文件) ===\n")
    if not dups:
        print("  ✅ 无重复编号")
        return 0
    print(f"  ⚠️ {len(dups)} 个编号被重复占用:")
    for k in sorted(dups, key=lambda x: int(re.sub(r"\D", "", x) or 0)):
        print(f"\n  {k} ({len(dups[k])} 个文件):")
        for p in sorted(dups[k]):
            sz = os.path.getsize(os.path.join(KB, p))
            print(f"     {sz:>8,}B  {p}")
    return len(dups)


def next_rid(count=1):
    m = scan_rids()
    nums = [int(re.sub(r"\D", "", k)) for k in m if re.sub(r"\D", "", k)]
    top = max(nums) if nums else 0
    if count == 1:
        print(f"下一个可用编号: r{top + 1}")
    else:
        print(f"预留 {count} 个编号: " + ", ".join(f"r{top+1+i}" for i in range(count)))
        print("\n★ 并行任务书应预先分配 (避免两个子代理用同一编号):")
        for i in range(count):
            print(f"   子代理 {i+1} → r{top+1+i}")
    return top + 1


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if check() == 0 else 1)
    elif "--next" in sys.argv:
        i = sys.argv.index("--next")
        n = 1
        if i + 1 < len(sys.argv) and sys.argv[i+1].isdigit():
            n = int(sys.argv[i+1])
        next_rid(n)
    else:
        print(__doc__)
