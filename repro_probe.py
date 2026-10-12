#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""repro_probe.py — 精确测量（修掉前一轮的正则构造 bug；先校准再判决 = MR5）"""
import os, re, json, sys
try:
    from _paths import ROOT as BASE, TOOLS_DIR, STATE_DIR, SANDBOX_DIR
except Exception:
    BASE = r'D:/hermes/analysis'; TOOLS_DIR=STATE_DIR=SANDBOX_DIR=BASE
A = os.path.join(BASE, 'PAPER_ARCHIVE_agent_memory_swarm_2026-10.md')
C = os.path.join(BASE, 'AGENT_MEMORY_COORD_DESIGN_CHECKLIST_v1.md')
t = open(A, encoding='utf-8', errors='replace').read()

print('=== 校准检查器本身（MR5）===')
# 已知输入 → 预期值
probe = '铁律 7 与 铁律 **12** 和 铁律142'
got = [int(x) for x in re.findall(r'铁律\s*\*{0,2}\s*(\d+)', probe)]
print(f'  校准: 输入 {probe!r} ⇒ 抽出 {got}  (期望 [7,12,142])  {"✅" if got==[7,12,142] else "❌ 检查器未校准"}')

print('\n=== ① 铁律 ===')
iron = [int(x) for x in re.findall(r'铁律\s*\*{0,2}\s*(\d+)', t)]
print(f'  全文 "铁律 N" 出现 {len(iron)} 次, 唯一值 {len(set(iron))} 个, 最大 {max(iron)}')
# 找 跨论文铁律 段落
m = re.search(r'^#+\s*跨论文铁律.*$', t, re.M)
if m:
    seg = t[m.start(): m.start()+20000]
    end = re.search(r'^#+\s', seg[5:], re.M)
    seg = seg[:end.start()+5] if end else seg
    rows = re.findall(r'^\s*[-*]?\s*\*{0,2}(\d{1,3})[\.\)、]', seg, re.M)
    print(f'  找到 `跨论文铁律` 段: {len(seg)} 字, 段内编号行 {len(rows)} 个')
    print(f'  段内最大的 5 个编号: {sorted(map(int,rows))[-5:] if rows else "—"}')
else:
    print('  ⚠️ 未找到 `跨论文铁律` 标题段')
# header 声称
for m in re.finditer(r'铁律[^。\n]{0,60}', t[:6000]):
    print(f'  header: {m.group(0).strip()[:110]}')

print('\n=== ② 文件体积（header 声称 vs 实测）===')
for m in re.finditer(r'[^。\n]{0,45}KB[^。\n]{0,45}', t[:8000]):
    print(f'  声称: {m.group(0).strip()[:120]}')
sz = os.path.getsize(A)
print(f'  实测: {sz} B = {sz/1024:.1f} KB = {sz/1024/1024:.3f} MB')
print(f'  ⇒ 比值 声称/实测 = {3150/(sz/1024):.2f}×' if 'KB' in t[:8000] else '')

print('\n=== ③ 清单 ===')
ct = open(C, encoding='utf-8', errors='replace').read()
szc = os.path.getsize(C)
print(f'  实测: {szc/1024:.0f} KB / {ct.count(chr(10))+1} 行 / {len(ct)} 字')
p1 = re.findall(r'\*\*\d+\s', ct)
print(f'  `**N ` 格式出现: {len(p1)}')
rows = re.findall(r'^\|\s*(\d{1,3})\s*\|', ct, re.M)
print(f'  表格首列数字行: {len(rows)}  最大 {max(map(int,rows)) if rows else 0}')
heads = re.findall(r'^#{3,4}\s*#?(\d{1,3})[\.\s:：]', ct, re.M)
print(f'  ###/#### 编号标题: {len(heads)}  最大 {max(map(int,heads)) if heads else 0}')
print(f'  ⇒ 归档 memory 声称: 347 条 / 最大 407')

print('\n=== ④ 条目数/编号连续性（复核 B1/B2）===')
h = re.findall(r'^###\s*#?(\d{1,3})[\.\s:：]', t, re.M)
u = sorted(set(int(x) for x in h))
print(f'  ### 编号条目 {len(h)} 条, 唯一 {len(u)}, 连续={u==list(range(1,u[-1]+1))}, 范围 1..{u[-1]}')
