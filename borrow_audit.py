# -*- coding: utf-8 -*-
"""借鉴项盘点 v2 — 宽松提取"""
import re, glob, os

base = r"D:\hermes\hermes-data\profiles\qqbot3\knowledge_base\research"
files = []
for pat in [r"r8[1-4]\d_.*\.md", r"r85[0-7]_.*\.md"]:
    files += glob.glob(os.path.join(base, pat))
items = []
for f in sorted(set(files)):
    name = os.path.basename(f)[:16]
    txt = open(f, encoding="utf-8", errors="ignore").read()
    # 借鉴标题行 (## 借鉴 N)
    for m in re.finditer(r"#{2,3}\s*借鉴\s*([0-9])\s*(?:🎯)?\s*\n(.{0,300}?)(?=\n#{2,3}|\n---|\Z)", txt, re.S):
        desc = re.sub(r"\s+", " ", m.group(2)).strip()
        items.append((name, m.group(1), desc[:150]))
    # 正文行内借鉴 (借鉴 N: ...)
    for m in re.finditer(r"借鉴\s*([0-9])\s*[：:]\s*(.{10,240})", txt):
        desc = re.sub(r"\s+", " ", m.group(2)).strip()
        if m.group(2).strip() not in [i[2] for i in items if i[0] == name]:
            items.append((name, m.group(1), desc[:150]))
print(f"总借鉴项: {len(items)}\n")
for name, n, desc in items:
    print(f"[{name}] #{n}: {desc}")
