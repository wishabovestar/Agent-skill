#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用归档融合器: 把一条 `### N.` 条目追加进主归档, 并现算重写头部计数。

用法: python merge_entry.py <entry.md> [archive.md]

- 追加到文件末尾 (归档以 ### N. 结尾, 无尾部审计表)
- 现算重写头部「共 **N 篇 + 1 本书**」(归档铁律: 计数不手维护)
- 保持原文件行尾风格
- 先备份
"""
import os
import re
import sys
import shutil
import datetime

ARCH_DEFAULT = 'D:/hermes/analysis/PAPER_ARCHIVE_agent_memory_swarm_2026-10.md'


def main():
    if len(sys.argv) < 2:
        print('用法: python merge_entry.py <entry.md> [archive.md]')
        return 1
    entry_p = sys.argv[1]
    arch = sys.argv[2] if len(sys.argv) > 2 else ARCH_DEFAULT

    if not os.path.exists(entry_p):
        print(f'✗ 条目文件不存在: {entry_p}')
        return 1
    entry = open(entry_p, encoding='utf-8').read()
    m = re.search(r'^###\s*#?(\d+)\.', entry, re.M)
    if not m:
        print('✗ 条目文件里找不到 `### N.` 头')
        return 1
    n_new = int(m.group(1))

    raw = open(arch, 'rb').read()
    nl = '\r\n' if b'\r\n' in raw[:5000] else '\n'
    t = raw.decode('utf-8', errors='replace')

    nums = [int(x) for x in re.findall(r'^###\s*#?(\d+)', t, re.M)]
    n_before = len(nums)
    if n_new in nums:
        print(f'✗ 编号 {n_new} 已存在, 拒绝重复追加')
        return 1
    if n_new != max(nums) + 1:
        print(f'⚠️ 编号跳号: 现有最大 {max(nums)}, 本条 {n_new} (期望 {max(nums)+1})')

    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = f'{arch}.bak_before_{n_new}_{ts}'
    shutil.copy2(arch, bak)
    print(f'备份 -> {bak}')

    t2 = t.rstrip('\r\n') + nl + entry.replace('\n', nl).lstrip('\r\n')
    n_after = len(re.findall(r'^###\s*#?\d+', t2, re.M))
    t2, k = re.subn(r'共 \*\*\d+ 篇 \+ 1 本书\*\*', f'共 **{n_after} 篇 + 1 本书**', t2, count=1)
    open(arch, 'wb').write(t2.encode('utf-8'))

    t3 = open(arch, encoding='utf-8', errors='replace').read()
    n3 = [int(x) for x in re.findall(r'^###\s*#?(\d+)', t3, re.M)]
    print(f'条目 {n_before} -> {n3 and len(n3)}  (新增 1)')
    print(f'头部计数重写 {k} 处 -> 共 {len(n3)} 篇')
    print(f'最大编号 {max(n3)}  重复 {len(n3)-len(set(n3))}  末条 ### {n3[-1]}')
    print(f'文件 {os.path.getsize(arch):,} B')
    return 0


if __name__ == '__main__':
    sys.exit(main())
