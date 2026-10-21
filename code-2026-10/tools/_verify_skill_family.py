#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验记忆 skill 家族的交叉引用图：所有 related_skills 是否都能解析到真实 skill。"""
import io, os, re, sys
from pathlib import Path

SK = Path(r'D:/hermes/hermes-data/profiles/mybot/skills')

FAMILY = ['hermes-memory-store-mechanics', 'hermes-memory-extension',
          'cortexmem-memory', 'memory-consolidation-engine',
          'sleep-daydream-runtime', 'hermes-kb', 'hermes-harness']

# 全量 skill 目录索引（用于解析引用）
all_dirs = {}
for p in SK.rglob('SKILL.md'):
    if '.archive' in p.parts:
        continue
    all_dirs[p.parent.name] = p

print(f"全部可用 skill: {len(all_dirs)}\n")
print("=== 家族交叉引用图 ===")
edges = {}
missing_global = []
for name in FAMILY:
    p = all_dirs.get(name)
    if not p:
        print(f"  ✗ {name}: SKILL.md 未找到")
        continue
    t = io.open(p, encoding='utf-8').read()
    m = re.match(r'^---\r?\n(.*?)\r?\n---\r?\n', t, re.S)
    fm = m.group(1) if m else ''
    rel = re.search(r'related_skills:\s*\[(.*?)\]', fm, re.S)
    refs = [x.strip() for x in rel.group(1).split(',')] if rel else []
    edges[name] = refs
    ver = re.search(r'version:\s*(\S+)', fm)
    print(f"  {name:32s} v{ver.group(1) if ver else '?':7s} → {len(refs)} 条引用")

print("\n=== 引用解析检查 ===")
bad = 0
for src, refs in edges.items():
    for r in refs:
        if not r:
            continue
        ok = r in all_dirs
        if not ok:
            bad += 1
        print(f"  {'✓' if ok else '✗'} {src:32s} → {r}" + ('' if ok else "   ← 不存在!"))

print(f"\n=== 结果: 断裂引用 {bad} 条 ===")

# 反向：谁引用了 family
print("\n=== 反向引用（谁提到 family） ===")
for name, p in sorted(all_dirs.items()):
    if name in FAMILY:
        continue
    t = io.open(p, encoding='utf-8', errors='replace').read()
    hit = [f for f in FAMILY if f in t]
    if hit:
        print(f"  {name}: {', '.join(hit)}")

sys.exit(1 if bad else 0)
