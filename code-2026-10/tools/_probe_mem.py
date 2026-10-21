#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探测 memory_extension 的存储后端到底有什么 (复用其自身连接, 不打印凭据)"""
import sys, io, time, json
ANALYSIS = r'D:/hermes/analysis'
sys.path.insert(0, ANALYSIS)

# 复用 sleep_consolidation.py 的 exec 方式加载
ns = {}
with io.open(ANALYSIS + '/memory_extension.py', 'r', encoding='utf-8', errors='replace') as f:
    exec(f.read(), ns)

me = ns['MemoryEngine']()
r = getattr(me, '_r', None)
print("=== 连接 ===")
print(f"  Redis 句柄: {'有' if r else '无'}")

if r:
    print("\n=== 记忆键 ===")
    total = 0
    for k in ('mem:lt:by_importance', 'mem:idx:all', 'mem:st:idx', 'mem:lt:idx', 'mem:short:idx', 'mem:long:idx'):
        try:
            t = r.type(k)
            if t == 'zset': n = r.zcard(k)
            elif t == 'set': n = r.scard(k)
            elif t == 'list': n = r.llen(k)
            elif t == 'hash': n = r.hlen(k)
            elif t == 'string': n = len(r.get(k) or '')
            else: n = None
            flag = '' if n else '  ← 空'
            print(f"  {k:26s} type={t:8s} n={n}{flag}")
        except Exception as e:
            print(f"  {k:26s} ERR {e}")
    try:
        ks = r.keys('mem:*')
        print(f"\n  mem:* 键总数 = {len(ks)}")
        for k in sorted(ks)[:25]:
            print(f"    {k} ({r.type(k)})")
    except Exception as e:
        print(f"  keys() ERR: {e}")
    try:
        print(f"\n  db size = {r.dbsize()}")
    except Exception as e:
        print(f"  dbsize ERR: {e}")

# ChromaDB
print("\n=== ChromaDB ===")
for attr in ('_chroma', '_c', '_collection', 'collection'):
    v = getattr(me, attr, None)
    if v is not None:
        print(f"  {attr}: {type(v).__name__}")
        try:
            print(f"    count = {v.count()}")
        except Exception:
            pass

# 直接调一次 consolidate(dry_run=True)
print("\n=== consolidate(dry_run=True) ===")
try:
    res = me.consolidate(dry_run=True)
    print("  " + json.dumps(res, ensure_ascii=False))
except Exception as e:
    print(f"  ERR: {type(e).__name__}: {e}")

# 看有没有 add/remember 被调用过
print("\n=== 类方法 ===")
print("  " + ', '.join(sorted(m for m in dir(me) if not m.startswith('__'))))
