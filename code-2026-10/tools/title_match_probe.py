# -*- coding: utf-8 -*-
"""验证 title_match 选消息是否真的能挑到贴题的助手消息（以 131 条消息的锂电会话为例）。"""
import re
import sqlite3

DB = r"D:/hermes/hermes-data/profiles/mybot/state.db"
SID = "20260720_154554_b94783b5"


def grams(s):
    g = set()
    for run in re.findall(r"[\u4e00-\u9fa5]+", s or ""):
        g.update(run[i:i + 2] for i in range(max(0, len(run) - 1)))
    g.update(w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9_]{1,}", s or ""))
    return g


c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
c.row_factory = sqlite3.Row
title = c.execute("select title from sessions where id=?", (SID,)).fetchone()["title"]
tt = grams(title)
L = [f"title = {title}  grams={len(tt)}"]
rows = c.execute("select content from messages where session_id=? and role='assistant'"
                 " and length(content)>150 order by id desc limit 60", (SID,)).fetchall()
best = sorted(((len(tt & grams(re.sub(r"\s+", " ", r["content"]))) / len(tt),
                re.sub(r"\s+", " ", r["content"])) for r in rows), key=lambda x: -x[0])[:5]
for i, (sc, t) in enumerate(best):
    L.append(f"  TOP{i} match={sc:.2f} :: {t[:120]}")
open(r"D:/hermes/analysis/_title_match.txt", "w", encoding="utf-8").write("\n".join(L))
print("ok")
