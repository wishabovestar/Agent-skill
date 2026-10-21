#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 State of AI Report 2026 条目融合进 CLI 主归档 (PAPER_ARCHIVE_agent_memory_swarm)。
- 追加到文件末尾 (归档以 ### N. 结尾, 无尾部审计表)
- 现算重写头部计数 (归档铁律: 计数不手维护)
- 保持原文件的行尾风格 (CRLF)
"""
import re, os, sys

A = '/mnt/d/hermes/analysis/PAPER_ARCHIVE_agent_memory_swarm_2026-10.md'
E = '/mnt/d/hermes/analysis/soai2026_entry.md'

raw = open(A, 'rb').read()
nl = '\r\n' if b'\r\n' in raw[:5000] else '\n'
t = raw.decode('utf-8', errors='replace')
entry = open(E, encoding='utf-8').read()

n_before = len(re.findall(r'^###\s*#?\d+', t, re.M))
print(f'融合前条目数 = {n_before}')
print(f'行尾风格 = {"CRLF" if nl == chr(13)+chr(10) else "LF"}')

# 追加
t2 = t.rstrip('\r\n') + nl + entry.replace('\n', nl).lstrip('\r\n')
n_after = len(re.findall(r'^###\s*#?\d+', t2, re.M))
print(f'融合后条目数 = {n_after}  (新增 {n_after - n_before})')

# 现算重写头部计数
new, k = re.subn(r'共 \*\*\d+ 篇 \+ 1 本书\*\*', f'共 **{n_after} 篇 + 1 本书**', t2, count=1)
print(f'头部计数重写 = {k} 处')
t2 = new

open(A, 'wb').write(t2.encode('utf-8'))
print(f'已写回: {A}  ({os.path.getsize(A)} B)')

# 复核
t3 = open(A, encoding='utf-8', errors='replace').read()
nums = [int(x) for x in re.findall(r'^###\s*#?(\d+)', t3, re.M)]
print(f'复核: 条目 {len(nums)}  最大编号 {max(nums)}  重复 {len(nums)-len(set(nums))}')
print(f'末条: ### {nums[-1]}')
