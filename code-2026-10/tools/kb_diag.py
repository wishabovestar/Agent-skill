#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hermes_kb.py 缺陷诊断 —— 只读+隔离, 绝不碰共享库
验证四条怀疑:
  D1 init() 每次 open 都跑 ⇒ 读操作也拿写锁?
  D2 search() 宽 except ⇒ FTS 语法错静默降级?
  D3 upsert_* 不 commit ⇒ 忘 commit 就丢数据?
  D4 open_kb('bare.db') ⇒ os.makedirs('') 崩?
"""
import os, sys, sqlite3, tempfile, shutil, traceback
sys.path.insert(0, r'D:/hermes/data/kb')
import hermes_kb as K

TMP = tempfile.mkdtemp(prefix='kbdiag_')
print(f'隔离工作区: {TMP}\n')
R = {}

# ── D4: 裸文件名 ──
print('═══ D4: open_kb("bare.db") ═══')
try:
    c = K.open_kb(os.path.join(TMP, 'a.db'))
    print('  ✅ 绝对路径 OK'); c.close()
except Exception as e:
    print(f'  ❌ {type(e).__name__}: {e}'); R['D4'] = f'{type(e).__name__}: {e}'
try:
    os.chdir(TMP)
    c = K.open_kb('bare.db')          # 相对名 ⇒ dirname == ''
    print('  ✅ 相对名 OK'); c.close()
except Exception as e:
    print(f'  ❌ 相对名崩: {type(e).__name__}: {e}'); R['D4_rel'] = f'{type(e).__name__}: {e}'

# ── D1: init() 在每次 open 时跑 ⇒ 会不会拿写锁 ──
print('\n═══ D1: open_kb() 是否触发写事务 ═══')
p = os.path.join(TMP, 'b.db')
c1 = K.open_kb(p)                      # 第一次: 建库
c1.execute("INSERT INTO entities(entity_type,name,label) VALUES('Concept','x','x')")
c1.commit()
before = os.path.getsize(p)
# 另一进程持写锁, 本进程再 open_kb() —— 若 open_kb 需要写锁则会 BLOCK/超时
locker = os.path.join(TMP, 'lock.py')
open(locker, 'w').write(f'''
import sqlite3, time
c = sqlite3.connect(r"{p}", timeout=1)
c.execute("BEGIN IMMEDIATE")      # 持写锁
print("  (锁进程已持写锁)", flush=True)
time.sleep(8)
c.rollback()
''')
import subprocess, time
pr = subprocess.Popen([sys.executable, locker], stdout=subprocess.PIPE, text=True)
time.sleep(1.5)
t0 = time.time()
try:
    c2 = K.open_kb(p)                  # 只读意图, 但 open_kb 会跑 init()
    dt = time.time() - t0
    print(f'  ⚠️ 在写锁被持时 open_kb() 仍返回, 耗时 {dt:.2f}s  ⇒ init() 的 commit 没被阻塞?')
    print(f'     (若耗时≈0 说明 executescript 的 DDL 都是 IF NOT EXISTS ⇒ 无写? 需再验)')
    c2.close()
    R['D1'] = f'open_kb 返回耗时 {dt:.2f}s'
except Exception as e:
    dt = time.time() - t0
    print(f'  ❌ open_kb() 在写锁下失败, 耗时 {dt:.2f}s: {type(e).__name__}: {e}')
    R['D1'] = f'BLOCKED {dt:.2f}s: {type(e).__name__}: {e}'
pr.wait()

# ── D1b: 直接测 init() 在写锁下是否阻塞 ──
print('\n═══ D1b: 显式跑 init() 在写锁下 ═══')
pr2 = subprocess.Popen([sys.executable, locker], stdout=subprocess.PIPE, text=True)
time.sleep(1.5)
try:
    c3 = K.connect(p, create=False)
    t0 = time.time(); K.init(c3); dt = time.time()-t0
    print(f'  init() 返回耗时 {dt:.2f}s')
    R['D1b'] = f'init {dt:.2f}s'
    c3.close()
except Exception as e:
    dt = time.time()-t0
    print(f'  ❌ init() 失败/阻塞 {dt:.2f}s: {type(e).__name__}: {e}')
    R['D1b'] = f'init FAIL {dt:.2f}s: {type(e).__name__}'
pr2.wait()

# ── D2: search() 宽 except 静默降级 ──
print('\n═══ D2: search() 对 FTS 语法错的处理 ═══')
c4 = K.open_kb(p)
c4.execute("INSERT INTO entities(entity_type,name,label,description) VALUES('Concept','alpha','A','hello world')")
c4.commit()
good = K.search(c4, 'alpha');      print(f'  正常查询 "alpha"  → {len(good)} 条')
bad  = K.search(c4, 'NEAR(');      print(f'  畸形查询 "NEAR("  → {len(bad)} 条  {bad[:1]}')
bad2 = K.search(c4, '"unclosed');  print(f'  畸形查询 \'"unclosed\' → {len(bad2)} 条')
print('  ⚠️ 若畸形查询没抛错而是返回(可能不同)结果 ⇒ 静默降级成立')
R['D2'] = f'"NEAR(" → {len(bad)} 条 (未报错)'
c4.close()

# ── D3: upsert_* 不 commit ⇒ 忘 commit 就丢 ──
print('\n═══ D3: upsert_entity 后不 commit ═══')
c5 = K.connect(p, create=False)
eid = K.upsert_entity(c5, 'Concept', 'no_commit_probe', 'P', 'probe')
print(f'  upsert 返回 id={eid}')
c5.close()            # 不 commit
c6 = K.connect(p, create=False)
row = c6.execute("SELECT COUNT(*) FROM entities WHERE name='no_commit_probe'").fetchone()[0]
print(f'  重开连接后该实体存在? {"存在 ✅" if row else "【不存在 ⇒ 数据丢了】❌"}')
R['D3'] = 'upsert 后不 commit ⇒ 数据丢失' if not row else 'upsert 自动提交(或 close 触发)'
c6.close()

# ── D5: 有无 close/上下文管理 ──
print('\n═══ D5: 连接生命周期 ═══')
print(f'  has __enter__ : {hasattr(c5, "__enter__")}')
print(f'  open_kb 返回类型: {type(c1).__name__} (sqlite3.Connection, 无封装)')
print(f'  模块里有无 close 封装: {"close" in dir(K)}')

shutil.rmtree(TMP, ignore_errors=True)
print('\n═══ 诊断结论 ═══')
for k in sorted(R): print(f'  {k}: {R[k]}')
