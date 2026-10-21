#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D2 决定性复测: search() 的宽 except 是否【静默降级】且返回【不同结果】
判别器设计(MR5 式): 造一个【FTS 会报错】且【LIKE 会命中】的输入
  ⇒ 若返回 >0 条 ⇒ 走了 except 分支(LIKE) ⇒ 静默降级成立
  ⇒ 若抛错     ⇒ 未降级
"""
import os, sys, sqlite3, tempfile, shutil
sys.path.insert(0, r'D:/hermes/data/kb')
import hermes_kb as K

TMP = tempfile.mkdtemp(prefix='kbdiag2_')
p = os.path.join(TMP, 't.db')
c = K.open_kb(p)
# 造数据: description 里含 FTS 语法非法字符 '*'
c.execute("INSERT INTO entities(entity_type,name,label,description) VALUES('Concept','star','S','contains a literal * asterisk')")
c.execute("INSERT INTO entities(entity_type,name,label,description) VALUES('Concept','plain','P','just plain text')")
c.commit()

print('═══ 直接问 SQLite: FTS 对 "*" 会怎样 ═══')
try:
    n = c.execute("SELECT count(*) FROM entities_fts WHERE entities_fts MATCH ?", ('*',)).fetchone()[0]
    print(f'  FTS MATCH "*" → {n} 条  ⇒ FTS【接受】该查询, 不会进 except')
    fts_ok = True
except Exception as e:
    print(f'  FTS MATCH "*" → 抛错 {type(e).__name__}: {e}  ⇒ 会进 except 分支')
    fts_ok = False

print('\n═══ search() 对 "*" 的返回 ═══')
r = K.search(c, '*')
print(f'  search("*") → {len(r)} 条: {[x["name"] for x in r]}')
print(f'  ⇒ 期望(FTS): {"0 条(语法无匹配)" if fts_ok else "抛错"}')
print(f'  ⇒ 实际: {len(r)} 条  {"⚠️ 走了 LIKE 降级(命中 star)" if len(r)>0 else ""}')

print('\n═══ ⭐ 更强判别器: 多词查询 (FTS 语义 vs LIKE 字面) ═══')
# FTS: 'alpha beta' = alpha AND beta (命中两词都有的)
# LIKE: '%alpha beta%' = 字面串 "alpha beta" (命中连写的)
c.execute("INSERT INTO entities(entity_type,name,label,description) VALUES('Concept','both','B','alpha and beta together')")
c.execute("INSERT INTO entities(entity_type,name,label,description) VALUES('Concept','literal','L','the phrase alpha beta literally')")
c.commit()
q = 'alpha beta'
r2 = K.search(c, q)
print(f'  search("{q}") → {len(r2)} 条: {[x["name"] for x in r2]}')
print(f'  FTS 语义应命中: both + literal (若 FTS 把两词当 AND/短语)')
n_fts = 0
try:
    n_fts = c.execute("SELECT count(*) FROM entities_fts WHERE entities_fts MATCH ?", (q,)).fetchone()[0]
    print(f'  直查 FTS 得 {n_fts} 条')
except Exception as e:
    print(f'  直查 FTS 抛错: {e}')
n_like = c.execute("SELECT count(*) FROM entities WHERE name LIKE ? OR description LIKE ?", (f'%{q}%', f'%{q}%')).fetchone()[0]
print(f'  直查 LIKE "%{q}%" 得 {n_like} 条')

print('\n═══ 结论 ═══')
print(f'  • except 分支存在且无任何日志/标记  = {"是" if True else "否"} (源码事实: line 163 裸 except)')
print(f'  • 降级是否可触发 = 见上 "*" 的结果')
print(f'  • 降级后结果是否【语义不同】= FTS {n_fts} 条 vs LIKE {n_like} 条 ⇒ {"不同 ⚠️" if n_fts!=n_like else "相同"}')

# 再验 upsert_rel 的同款问题
print('\n═══ D3b: upsert_rel 是否也不 commit ═══')
a = K.upsert_entity(c, 'Concept', 'A'); b = K.upsert_entity(c, 'Concept', 'B')
c.commit()
K.upsert_rel(c, a, b, 'RELATED_TO')
c.close()
c2 = K.connect(p, create=False)
n = c2.execute('SELECT count(*) FROM relationships').fetchone()[0]
print(f'  upsert_rel 后不 commit → 关系表 {n} 条 ⇒ {"丢了 ❌" if n==0 else "在"}')
c2.close()
shutil.rmtree(TMP, ignore_errors=True)
