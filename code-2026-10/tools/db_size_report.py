#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only size breakdown of a Hermes profile state.db.

Answers: is the file big because of DATA, or because of reclaimable free pages
(i.e. would VACUUM help)?  Opens read-only + immutable-tolerant so it never
disturbs a live gateway.
"""
import os
import sqlite3
import sys

ROOT = r"D:\hermes\hermes-data\profiles"


def report(profile):
    path = os.path.join(ROOT, profile, "state.db")
    print("=" * 78)
    print(f"{profile}   {path}")
    if not os.path.isfile(path):
        print("  absent")
        return
    print(f"  file size      : {os.path.getsize(path)/1e9:.2f} GB")
    for side in ("-wal", "-shm"):
        p = path + side
        if os.path.exists(p):
            print(f"  {side:<14}: {os.path.getsize(p)/1e6:.1f} MB")
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=8)
    except Exception as e:
        print(f"  !! cannot open: {e}")
        return
    c = conn.cursor()

    def one(sql, label):
        try:
            v = c.execute(sql).fetchone()
            print(f"  {label:<24}: {v[0] if v else '?'}")
        except Exception as e:
            print(f"  {label:<24}: ERR {e}")

    ps = c.execute("PRAGMA page_size").fetchone()[0]
    pc = c.execute("PRAGMA page_count").fetchone()[0]
    fl = c.execute("PRAGMA freelist_count").fetchone()[0]
    print(f"  page_size              : {ps}")
    print(f"  page_count             : {pc}   (= {pc*ps/1e9:.2f} GB)")
    print(f"  freelist (reclaimable) : {fl}   (= {fl*ps/1e6:.1f} MB  -> VACUUM reclaims this)")

    print("  -- tables by row count --")
    try:
        tables = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    except Exception as e:
        print(f"     ERR {e}")
        tables = []
    rows = []
    for t in tables:
        try:
            n = c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            rows.append((n, t))
        except Exception:
            pass
    rows.sort(reverse=True)
    for n, t in rows[:18]:
        print(f"     {n:>12,}  {t}")

    print("  -- tables by stored bytes (dbstat, may take a moment) --")
    try:
        tot = c.execute(
            "SELECT name, SUM(pgsize) b FROM dbstat GROUP BY name ORDER BY b DESC LIMIT 18").fetchall()
        for name, b in tot:
            print(f"     {b/1e6:>10.1f} MB  {name}")
    except Exception as e:
        print(f"     dbstat unavailable: {e}")

    conn.close()


if __name__ == "__main__":
    for p in (sys.argv[1:] or ["qqbot3", "mybot", "qqbot2", "qqbot4", "qqbot5"]):
        report(p)
