#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""压缩 arXiv HTML 去标签文本里的表格：把「一格一行」还原成「一行一法」。

用法: python parse_paper_tables.py papers/2610.15772v1.txt 352 1300
输出: 每条方法名 + 其后紧跟的数值串（保留原始顺序），便于人工核对。
纪律: 只做搬运与压缩，不改数字；解析不出的行原样打出（不静默丢弃）。
"""
import sys


def is_num(s):
    t = s.strip().replace('$', '').replace('*', '').replace('\u2212', '-').replace('\u2013', '-')
    t = t.replace('x', 'x')
    if not t:
        return False
    body = t.split('±')[0].split('+/-')[0].strip().rstrip('%')
    try:
        float(body)
        return True
    except ValueError:
        return False


def main():
    path = sys.argv[1]
    lo = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    hi = int(sys.argv[3]) if len(sys.argv) > 3 else 10 ** 9
    L = [s.strip() for s in open(path, encoding='utf-8').read().split('\n')]
    name, nums = None, []
    out = []

    def flush():
        if name is not None and nums:
            out.append(f'{name[:26]:<26}| ' + ' '.join(nums))

    for i in range(lo - 1, min(hi, len(L))):
        s = L[i]
        if not s:
            continue
        if is_num(s):
            nums.append(s.replace('$', '').replace('*', ''))
        else:
            flush()
            name, nums = s, []
    flush()
    print(f'# 区间 {lo}-{hi}｜压缩后 {len(out)} 行')
    print('\n'.join(out))


if __name__ == '__main__':
    main()
