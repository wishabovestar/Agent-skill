#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RSIPO 取数：把需要亲验的正文段落/表行落到 digest 文件，再由 read_file 读取。
不改数字、不解析不出就原样打出。"""
import re, sys

SRC = "papers/2610.15772v1.txt"
OUT = "_rsipo_digest.txt"

lines = open(SRC, encoding="utf-8").read().split("\n")
N = len(lines)

def p(*a):
    print(*a)

buf = []
def w(s=""):
    buf.append(s)

w(f"# RSIPO digest — 源 {SRC} 共 {N} 行")
w()

w("## A. 小节/表/图标题地图（全篇）")
pat = re.compile(r"^(Table \d+|Figure \d+|Algorithm \d+)\s*[:.]|^(\d+(\.\d+)*)\s+[A-Z][a-z]|^[A-E](\.\d+)?\s+[A-Z]")
for i, s in enumerate(lines, 1):
    t = s.strip()
    if not t:
        continue
    if re.match(r"^(Abstract|Introduction|Related Work|Preliminaries|Method|Experiments?|Conclusion|Limitations|References|Appendix)", t) and len(t) < 60:
        w(f"{i:6d}| [SEC] {t[:90]}")
    elif re.match(r"^(Table|Figure|Algorithm)\s+\d+\s*:", t):
        w(f"{i:6d}| [CAP] {t[:110]}")
    elif re.match(r"^[A-E](\.\d+)?\s+[A-Z]", t) and len(t) < 80:
        w(f"{i:6d}| [SUB] {t[:90]}")
w()

w("## B. 句子流（len>70，过滤表格单元）—— 172–352（Intro/Method）")
for i in range(171, 352):
    s = lines[i].strip()
    if len(s) > 70:
        w(f"{i+1:6d}| {s}")
w()

w("## C. 句子流 —— 380–860（4.1 设定 + 4.2 主结果讨论，Qwen2.5-7B 表前后）")
for i in range(379, 860):
    s = lines[i].strip()
    if len(s) > 80 and not re.match(r"^(Table|Figure)", s):
        w(f"{i+1:6d}| {s}")
w()

w("## D. 句子流 —— 1060–1330（主结果讨论尾 / 4.3 分析 / 消融 / 结论 / 局限）")
for i in range(1059, min(1330, N)):
    s = lines[i].strip()
    if len(s) > 60:
        w(f"{i+1:6d}| {s}")
w()

w("## E. 关键词行（种子/重复/误差棒/复现/成本/GPU）")
kw = re.compile(r"seed|repeated|three runs|error bar|standard deviation|confidence|re-?implement|reproduc|overhead|cost|budget|H20|GPU|warm|steps per|learning rate|KL", re.I)
for i, s in enumerate(lines, 1):
    t = s.strip()
    if kw.search(t) and 40 < len(t) < 300:
        w(f"{i:6d}| {t}")
w()

w("## F. 附录：Qwen2.5-3B 表原样行（1885–2000）")
for i in range(1884, min(2000, N)):
    s = lines[i].rstrip()
    if s.strip():
        w(f"{i+1:6d}| {s[:160]}")
w()

w("## G. 附录 D 训练动力学表原样行（2440–2560）")
for i in range(2439, min(2560, N)):
    s = lines[i].rstrip()
    if s.strip():
        w(f"{i+1:6d}| {s[:160]}")

open(OUT, "w", encoding="utf-8").write("\n".join(buf) + "\n")
p(f"OK → {OUT}  {len(buf)} 行  {len(chr(10).join(buf))} 字符")
