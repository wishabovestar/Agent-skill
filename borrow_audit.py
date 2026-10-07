# -*- coding: utf-8 -*-
"""借鉴项盘点 v3 — 全库扫描 + 零结果守卫

★ 2026-09-28 修复 v2 的两个致命缺陷（实测，非推断）:
  ① 【窗口过期】v2 只扫 `r8[1-4]\\d_.*\\.md` + `r85[0-7]_.*\\.md` ⇒ 仅覆盖 r810–r857。
     实测 research 下 r*_.md 共 1,603–1,619 档, 其中窗口内仅 48 档 ⇒ **漏扫 97%**。
  ② 【正则转义误用于 glob】两条模式里的 `\\d` 与 `\\.` 在 glob 中都是
     【字面反斜杠+字符】而非"数字/点"。文件名不含反斜杠 ⇒ **两条模式恒不匹配**。
     实测: `r85[0-7]_.*\\.md` 命中 0, 而 `r85[0-7]_*.md` 命中 8。
  ⇒ 两缺陷叠加使 v2 **恒输出「总借鉴项: 0」**, 在 100% 漏报下看起来像"本机没有借鉴项"。

★ 本版原则: 扫全库 + 零结果必须显式区别于"没数据"。
  ★ 判据: 盘点工具输出 0 时, 必须同时给出【扫描分母】, 否则无法区分
    "真的没有" 与 "没扫到"。这与本库既有失守模式「零采集静默」同族。
"""
# side_effects: [无写入]
import glob
import os
import re
import sys

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "knowledge_base", "research")

# ★ 标题式: `## 借鉴 N`
RE_H_TITLE = re.compile(r"#{2,3}\s*借鉴\s*([0-9])")
# ★ 行内式: `借鉴 N: ...`
RE_INLINE = re.compile(r"借鉴\s*([0-9])\s*[：:]\s*(.{10,240})")


def main():
    if not os.path.isdir(BASE):
        print("🔴 盘点失败: 目标目录不存在 — %s" % BASE)
        return 1

    # ★ glob 正确写法: 用 `[0-9]` 与 `*`, 不用 `\d` 与 `\.`
    files = sorted(set(glob.glob(os.path.join(BASE, "r*_*.md"))))
    if not files:
        print("🔴 盘点失败: 扫到 0 档 (分母为 0 ⇒ 结果不可解释, 需人工核查路径与模式)")
        return 1

    items = []
    for f in files:
        name = os.path.basename(f)[:16]
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for m in RE_H_TITLE.finditer(txt):
            items.append((name, m.group(1), ""))
        for m in RE_INLINE.finditer(txt):
            desc = re.sub(r"\s+", " ", m.group(2)).strip()
            items.append((name, m.group(1), desc[:150]))

    # ★ 分母必须与结果同时报出
    print("扫描分母: %d 档 (目录 %s)" % (len(files), BASE))
    print("总借鉴项: %d 处, 涉及 %d 档\n" % (len(items), len(set(i[0] for i in items))))

    if not items:
        # ★ 零结果守卫: 显式说明"不是没扫到", 而是"扫到 N 档但确实没有标记"
        print("★ 零结果说明: 已实扫 %d 档, 其中未发现「借鉴 N」标记。" % len(files))
        print("  这【不是】扫描失败 —— 分母已给出；若预期应有内容, 请核查标记格式是否变更。")
        return 0

    for name, n, desc in items:
        print("[%s] #%s: %s" % (name, n, desc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
