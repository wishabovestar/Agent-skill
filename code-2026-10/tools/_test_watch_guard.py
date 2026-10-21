# -*- coding: utf-8 -*-
"""看门狗负向自检：把 get() 打桩成反爬页/短正文/正常页，确认 chapter() 真的会失败。
判据必须能失败 —— 若三种输入都返回 body，则本次修复无效。"""
import importlib.util

P = r"D:/hermes/hermes-data/profiles/mybot/scripts/novel644550_watch.py"
spec = importlib.util.spec_from_file_location("watch", P)
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

CASES = [
    ("反爬简中", '<article class="page-content"><p>正在验证浏览器</p></article>'),
    ("反爬繁中", '<article class="page-content"><p>請稍等，正在進行安全驗證…</p></article>'),
    ("短正文", '<article class="page-content"><p>只有一句。</p></article>'),
]

for name, html in CASES:
    w.get = lambda *a, **k: html
    try:
        t, b = w.chapter(999)
        print("FAIL %s -> 竟然通过，body=%d" % (name, len(b)))
    except Exception as e:
        print("PASS %s -> %s" % (name, e))

good = '<article class="page-content"><p>第999章 测试</p>' + "<p>正文内容。</p>" * 150 + "</article>"
w.get = lambda *a, **k: good
try:
    t, b = w.chapter(999)
    print("PASS 正常页 -> title=%r chars=%d（标题已去重=%s）" % (t, len(b), not b.startswith(t)))
except Exception as e:
    print("FAIL 正常页被误杀 -> %s" % e)
