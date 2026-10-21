# -*- coding: utf-8 -*-
"""正向端到端：用真网络抓 583，但写进临时文件（不碰正式 full.txt）。
验证：① 能抓到正文 ② 追加格式正确 ③ last_max 连续推进到 583。"""
import importlib.util
import io
import json
import os

P = r"D:/hermes/hermes-data/profiles/mybot/scripts/novel644550_watch.py"
TMP = r"D:/hermes/hermes-data/profiles/mybot/cache/scratch"

spec = importlib.util.spec_from_file_location("watch", P)
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

w.FULL = os.path.join(TMP, "_e2e_full.txt")
w.STATE = os.path.join(TMP, "_e2e_state.json")
w.LOG = os.path.join(TMP, "_e2e_log.txt")
for p in (w.FULL, w.LOG):
    if os.path.exists(p):
        os.remove(p)
json.dump({"last_max": 582, "total_chars": 0, "fails": 0}, io.open(w.STATE, "w", encoding="utf-8"))

w.toc = lambda: ([582, 583], {583: "第583章 皋月的新办公室"})
rc = w.main()
print("rc =", rc)
print("state =", io.open(w.STATE, encoding="utf-8").read())
txt = io.open(w.FULL, encoding="utf-8").read()
print("full chars =", len(txt), "| 标题行数 =", txt.count("第583章"))
print("head =", repr(txt[:80]))
print("tail =", repr(txt[-60:]))
