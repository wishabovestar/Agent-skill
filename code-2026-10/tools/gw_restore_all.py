#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Restore all Hermes gateways after the 2026-09-17 total outage.

Sequence (per the gateway-watchdog-v2 skill):
  1. back up locks + states (rollback material)
  2. remove the 9 ORPHAN lock files (holders are dead -> they block every start)
  3. disarm the weixin lock stealers (qqbot4/qqbot5 still have weixin/accounts/)
  4. sanitise every state.json: pid=0, gateway_state=stopped, platforms disconnected
  5. start the gateways one at a time, DETACHED, PYTHONUTF8=1, verify each
  6. report

Never prints credential values.
"""
import ctypes
import datetime
import glob
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = r"D:\hermes\hermes-data\profiles"
LOCKS = r"C:\Users\Administrator\.local\state\hermes\gateway-locks"
BK = r"D:\hermes\analysis\gw_restore_backup_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
HERMES = r"C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe"

# profiles in the skill's recovery order: simplest first, weixin carrier before
# the 3-platform monster, dormant ones last.
ORDER = ["qqbot4", "qqbot2", "qqbot3", "mybot", "qqbot5", "dong", "wenming"]

kernel32 = ctypes.windll.kernel32
STILL_ACTIVE = 259


def alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    h = kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return False
    code = ctypes.c_ulong()
    ok = kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    kernel32.CloseHandle(h)
    return bool(ok) and code.value == STILL_ACTIVE


def log(m):
    print(m, flush=True)


os.makedirs(BK, exist_ok=True)
os.makedirs(os.path.join(BK, "locks"), exist_ok=True)
os.makedirs(os.path.join(BK, "states"), exist_ok=True)

print("=" * 78)
print("GATEWAY RESTORE  " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("backup dir: " + BK)
print("=" * 78)

# ---------------------------------------------------------------- 1. backup
log("\n### 1. BACKUP")
n = 0
for f in glob.glob(os.path.join(LOCKS, "*.lock")):
    shutil.copy2(f, os.path.join(BK, "locks", os.path.basename(f)))
    n += 1
log(f"  locks backed up: {n}")
for p in ORDER:
    sp = os.path.join(ROOT, p, "gateway_state.json")
    if os.path.isfile(sp):
        shutil.copy2(sp, os.path.join(BK, "states", p + ".json"))
log("  states backed up")

# ---------------------------------------------------------------- 2. locks
log("\n### 2. REMOVE ORPHAN LOCKS (all holders verified dead)")
for f in sorted(glob.glob(os.path.join(LOCKS, "*.lock"))):
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        d = {}
    pid = d.get("pid")
    if alive(pid):
        log(f"  KEEP   {os.path.basename(f)}  holder pid={pid} ALIVE")
        continue
    try:
        os.remove(f)
        log(f"  REMOVED {os.path.basename(f)}  (dead pid={pid}, home={os.path.basename(d.get('hermes_home','?'))})")
    except Exception as e:
        log(f"  !! FAILED to remove {f}: {e}")

# ---------------------------------------------------------------- 3. weixin accounts
log("\n### 3. DISARM WEIXIN LOCK STEALERS (config-disabled but accounts/ auto-loads)")
CARRIER = "qqbot3"
for p in ORDER:
    acc = os.path.join(ROOT, p, "weixin", "accounts")
    if not os.path.isdir(acc):
        continue
    files = os.listdir(acc)
    if not files:
        continue
    if p == CARRIER:
        log(f"  KEEP   {p}/weixin/accounts ({len(files)} file(s))  <- designated weixin carrier")
        continue
    dst = os.path.join(ROOT, p, "weixin", "accounts.disabled." +
                       datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    try:
        shutil.move(acc, dst)
        log(f"  MOVED  {p}/weixin/accounts -> {os.path.basename(dst)}  ({len(files)} file(s))")
    except Exception as e:
        log(f"  !! FAILED to move {acc}: {e}")

# ---------------------------------------------------------------- 4. states
log("\n### 4. SANITISE STATE (kill the false-alive)")
for p in ORDER:
    sp = os.path.join(ROOT, p, "gateway_state.json")
    if not os.path.isfile(sp):
        log(f"  {p}: no state file")
        continue
    try:
        d = json.load(open(sp, encoding="utf-8", errors="replace"))
    except Exception as e:
        log(f"  {p}: unreadable ({e})")
        continue
    d["pid"] = 0
    d["gateway_state"] = "stopped"
    for k in d.get("platforms", {}):
        d["platforms"][k]["state"] = "disconnected"
        d["platforms"][k]["error_message"] = "state reset (total outage recovery)"
    json.dump(d, open(sp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    log(f"  {p}: pid=0 state=stopped platforms->disconnected")

# ---------------------------------------------------------------- 5. start
log("\n### 5. START GATEWAYS (detached, PYTHONUTF8=1, one at a time)")

env = dict(os.environ)
env["PYTHONUTF8"] = "1"
env["PYTHONIOENCODING"] = "utf-8"

DETACHED = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS|NEW_PROCESS_GROUP|NO_WINDOW
HIDE = 0x08000000


def start(profile):
    cwd = r"D:\hermes\hermes-data"
    args = [HERMES, "--profile", profile, "gateway", "run"]
    try:
        p = subprocess.Popen(args, cwd=cwd, env=env,
                             creationflags=DETACHED | HIDE,
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             close_fds=True)
        return p.pid
    except Exception as e:
        log(f"    Popen failed: {e}")
        return None


results = {}
for i, p in enumerate(ORDER):
    log(f"\n  --- {p} ---")
    sp = os.path.join(ROOT, p, "gateway_state.json")
    launcher_pid = start(p)
    log(f"    launcher pid={launcher_pid}; waiting up to 75s for state to report a live pid")
    ok = False
    for _ in range(75):
        time.sleep(1)
        try:
            d = json.load(open(sp, encoding="utf-8", errors="replace"))
        except Exception:
            continue
        pid = d.get("pid")
        if pid and alive(pid):
            plats = d.get("platforms", {})
            conn = [k for k, v in plats.items() if v.get("state") == "connected"]
            log(f"    OK  pid={pid} alive=True  platforms={conn}")
            results[p] = ("up", pid, conn)
            ok = True
            break
    if not ok:
        log(f"    !! state never reported a live pid within 75s")
        results[p] = ("fail", None, [])
    time.sleep(8)

# ---------------------------------------------------------------- 6. report
print("\n" + "=" * 78)
print("RESULT")
print("=" * 78)
for p in ORDER:
    st, pid, conn = results.get(p, ("?", None, []))
    flag = "UP  " if st == "up" else "DOWN"
    print(f"  [{flag}] {p:<9} pid={str(pid):<7} {','.join(conn) if conn else '-'}")

print("\nfinal lock holders:")
for f in sorted(glob.glob(os.path.join(LOCKS, "*.lock"))):
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    print(f"  {d.get('scope','?'):<18} {os.path.basename(d.get('hermes_home','?')):<9} "
          f"pid={d.get('pid')} alive={alive(d.get('pid'))}")
print("\nDONE")
