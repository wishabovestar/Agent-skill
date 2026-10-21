#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Time PRAGMA quick_check(1) on a state.db, with a hard cap.

Shows whether a "slow startup" is genuine I/O slowness or a real block.
Read-only, so it never disturbs a running gateway.
"""
import sqlite3
import sys
import time

path = sys.argv[1]
cap = int(sys.argv[2]) if len(sys.argv) > 2 else 180

print(f"file: {path}")
print(f"cap : {cap}s")
t0 = time.time()
try:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    c = conn.cursor()
    print(f"  connect ok in {time.time()-t0:.2f}s")
    # journal mode tells us whether a hot WAL / locking is involved
    for p in ("journal_mode", "page_size", "page_count", "freelist_count", "wal_autocheckpoint"):
        try:
            print(f"  {p} = {c.execute('PRAGMA ' + p).fetchone()[0]}")
        except Exception as e:
            print(f"  {p} ERR {e}")
    c.execute("SELECT 1").fetchone()
    print(f"  trivial read ok in {time.time()-t0:.2f}s")
finally:
    pass

print(f"\nrunning PRAGMA quick_check(1) with a {cap}s cap...")
t1 = time.time()
done = False
try:
    conn.setprogresshandler(lambda: (_ for _ in ()).throw(TimeoutError("cap reached"))
                            if (time.time() - t1) > cap else None, 2000)
except Exception:
    pass
try:
    row = conn.execute("PRAGMA quick_check(1)").fetchone()
    print(f"  RESULT after {time.time()-t1:.1f}s: {row}")
    done = True
except Exception as e:
    print(f"  ABORTED after {time.time()-t1:.1f}s: {type(e).__name__}: {e}")
if not done:
    print("  -> quick_check did NOT finish within the cap: the startup block is real")
else:
    print("  -> quick_check completes; the startup slowness is genuine I/O cost")

print(f"\ntotal elapsed {time.time()-t0:.1f}s")
