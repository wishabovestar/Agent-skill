#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hermes_kb.py 修复的【正负对照】
  新文件(kb_new) 每个探针必须 PASS
  旧文件(kb_old) 每个探针必须被抓到 FAIL —— 否则探针是装饰品, 不算验证
全程独立进程 + 隔离临时库, 不碰共享库。
"""
import os, sys, sqlite3, tempfile, shutil, importlib.util, subprocess, textwrap

NB = r'D:/hermes/analysis/kb_controls_nb.py'
OLDF = r'D:/hermes/data/kb/hermes_kb.py.bak_20261012_003558'
NEWF = r'D:/hermes/data/kb/hermes_kb.py'

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def probes(K, tmp, tag):
    """返回每项探针的 (passed, detail)。PASS = 行为正确。"""
    R = {}
    # P1: 裸文件名不崩
    try:
        os.chdir(tmp)
        c = K.open_kb('bare_%s.db' % tag); c.close()
        R['P1_裸文件名'] = (True, '不崩')
    except Exception as e:
        R['P1_裸文件名'] = (False, f'{type(e).__name__}: {str(e)[:60]}')
    # P2: upsert 默认持久化
    p = os.path.join(tmp, 'b_%s.db' % tag)
    c = K.open_kb(p)
    try:
        K.upsert_entity(c, 'Concept', 'persist_probe', 'P', 'probe')
        c.close()
        c2 = K.connect(p, create=False)
        n = c2.execute("SELECT COUNT(*) FROM entities WHERE name='persist_probe'").fetchone()[0]
        c2.close()
        R['P2_upsert默认提交'] = (n == 1, f'重开后存在={bool(n)}')
    except Exception as e:
        R['P2_upsert默认提交'] = (False, f'{type(e).__name__}: {str(e)[:60]}')
    # P3: upsert_rel 默认持久化
    c = K.connect(p, create=False)
    try:
        a = K.upsert_entity(c, 'Concept', 'ra'); b = K.upsert_entity(c, 'Concept', 'rb')
        K.upsert_rel(c, a, b, 'RELATED_TO')
        c.close()
        c2 = K.connect(p, create=False)
        n = c2.execute('SELECT COUNT(*) FROM relationships').fetchone()[0]
        c2.close()
        R['P3_upsert_rel默认提交'] = (n >= 1, f'关系数={n}')
    except Exception as e:
        R['P3_upsert_rel默认提交'] = (False, f'{type(e).__name__}: {str(e)[:60]}')
    # P4: FTS 降级必须出声
    c = K.connect(p, create=False)
    try:
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            r = K.search(c, '*')
        spoken = len(buf.getvalue()) > 0
        R['P4_降级出声'] = (spoken, f'stderr {"有告警" if spoken else "【静默!】"} 返回{len(r)}条')
    except Exception as e:
        R['P4_降级出声'] = (False, f'{type(e).__name__}: {str(e)[:60]}')
    # P5: with_mode 可区分
    try:
        r = K.search(c, 'ra', with_mode=True)
        modes = {x.get('_mode') for x in r}
        R['P5_with_mode标记'] = (modes <= {'fts', 'like_degraded'} and len(modes) > 0, f'modes={modes}')
    except Exception as e:
        R['P5_with_mode标记'] = (False, f'{type(e).__name__}: {str(e)[:60]}')
    # P6: 非 OperationalError 不该被吞
    try:
        K.search(c, 'x', limit='not-an-int')     # 会抛 InterfaceError/TypeError
        R['P6_非语法错不被吞'] = (False, '【被吞了】应上抛')
    except sqlite3.OperationalError:
        R['P6_非语法错不被吞'] = (False, '被当作 FTS 语法错吞掉')
    except Exception:
        R['P6_非语法错不被吞'] = (True, '正确上抛')
    c.close()
    return R

def run_one(path, name):
    code = textwrap.dedent(f'''
        import sys, json, tempfile, shutil, importlib.util, os
        sys.path.insert(0, r"D:/hermes/analysis")
        import kb_controls_nb as C
        spec = importlib.util.spec_from_file_location("{name}", r"{path}")
        K = importlib.util.module_from_spec(spec); spec.loader.exec_module(K)
        tmp = tempfile.mkdtemp(prefix="ctl_{name}_")
        try:
            R = C.probes(K, tmp, "{name}")
        finally:
            os.chdir(tempfile.gettempdir()); shutil.rmtree(tmp, ignore_errors=True)
        print("@@@" + json.dumps(R, ensure_ascii=False))
    ''')
    p = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', cwd=r'D:/hermes/analysis')
    for line in (p.stdout or '').splitlines():
        if line.startswith('@@@'):
            return json.loads(line[3:])
    return {'_error': (p.stdout or '')[-300:] + (p.stderr or '')[-500:]}

import json
print('═══ 负对照: 旧文件 (改前 ad30aa3ea3ebc9a2) ═══')
old = run_one(OLDF, 'oldkb')
for k, v in old.items(): print(f'  {"✅" if v[0] else "❌"} {k:<22} {v[1]}')
print('\n═══ 正对照: 新文件 (改后) ═══')
new = run_one(NEWF, 'newkb')
for k, v in new.items(): print(f'  {"✅" if v[0] else "❌"} {k:<22} {v[1]}')

print('\n═══ 对照判决 ═══')
caught = [k for k in old if k in new and (not old[k][0]) and new[k][0]]
always_pass = [k for k in old if k in new and old[k][0] and new[k][0]]
decor = [k for k in new if new[k][0] and k not in caught]
print(f'  ⭐ 旧 FAIL → 新 PASS (探针有效, 修好了): {len(caught)}/{len(new)}')
for k in caught: print(f'      · {k}: 旧[{old[k][1][:44]}] → 新[{new[k][1][:44]}]')
if always_pass: print(f'  ℹ️ 两版都 PASS (该探针不区分版本): {always_pass}')
if decor: print(f'  ⚠️ 未被旧版检验的探针: {[k for k in decor if k not in caught]}')
