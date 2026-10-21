#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Restart ONE profile's gateway with stdout/stderr captured to a file.

The first restore pass redirected the child's stdout/stderr to DEVNULL, so a
startup hang left no trace. This captures everything so the next failure is
diagnosable.
"""
import ctypes
import datetime
import json
import os
import subprocess
import sys
import time

ROOT = r"D:\hermes\hermes-data\profiles"
HERMES = r"C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe"
LOGDIR = r"D:\hermes\analysis\gw_capture"
os.makedirs(LOGDIR, exist_ok=True)

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


def kill_tree(profile):
    """Kill every process whose command line mentions this profile + gateway."""
    ps = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*gateway*' -and "
         "$_.CommandLine -like '*" + profile + "*' } | ForEach-Object { $_.ProcessId }"],
        capture_output=True)
    pids = [int(x) for x in ps.stdout.decode().split() if x.strip().isdigit()]
    for pid in pids:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True, creationflags=0x08000000)
    return pids


def main():
    profile = sys.argv[1]
    print("=" * 78)
    print(f"RESTART WITH CAPTURE: {profile}   {datetime.datetime.now():%H:%M:%S}")
    print("=" * 78)

    killed = kill_tree(profile)
    print(f"  killed pids: {killed}")
    time.sleep(4)

    sp = os.path.join(ROOT, profile, "gateway_state.json")
    # reset state so we can tell whether THIS run wrote it
    try:
        d = json.load(open(sp, encoding="utf-8", errors="replace"))
        d["pid"] = 0
        d["gateway_state"] = "stopped"
        for k in d.get("platforms", {}):
            d["platforms"][k]["state"] = "disconnected"
            d["platforms"][k]["error_message"] = "restart-with-capture reset"
        json.dump(d, open(sp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print("  state reset")
    except Exception as e:
        print(f"  state reset failed: {e}")

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outf = os.path.join(LOGDIR, f"{profile}_{ts}.out.txt")
    errf = os.path.join(LOGDIR, f"{profile}_{ts}.err.txt")
    fo = open(outf, "wb")
    fe = open(errf, "wb")

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"

    DETACHED = 0x00000008 | 0x00000200 | 0x08000000
    p = subprocess.Popen([HERMES, "--profile", profile, "gateway", "run"],
                         cwd=r"D:\hermes\hermes-data", env=env,
                         creationflags=DETACHED,
                         stdin=subprocess.DEVNULL, stdout=fo, stderr=fe)
    print(f"  launcher pid={p.pid}")
    print(f"  stdout -> {outf}")
    print(f"  stderr -> {errf}")

    print("  waiting up to 330s for a live pid + running state...")
    print("  (a 2.5GB state.db costs ~3 min in PRAGMA quick_check after an unclean exit)")
    ok = False
    for i in range(330):
        time.sleep(1)
        try:
            d = json.load(open(sp, encoding="utf-8", errors="replace"))
        except Exception:
            continue
        pid = d.get("pid")
        if pid and alive(pid) and d.get("gateway_state") == "running":
            conn = [k for k, v in d.get("platforms", {}).items() if v.get("state") == "connected"]
            print(f"  OK after {i+1}s: pid={pid} gw=running platforms={conn}")
            ok = True
            break
    if not ok:
        try:
            d = json.load(open(sp, encoding="utf-8", errors="replace"))
            print(f"  !! not running after 100s: pid={d.get('pid')} alive={alive(d.get('pid'))} "
                  f"gw={d.get('gateway_state')}")
        except Exception as e:
            print(f"  !! state unreadable: {e}")

    fo.flush(); fe.flush()
    for f, label in ((outf, "STDOUT"), (errf, "STDERR")):
        try:
            txt = open(f, encoding="utf-8", errors="replace").read()
        except Exception:
            txt = ""
        print(f"\n  ---- {label} ({len(txt)} chars) ----")
        print("\n".join(txt.splitlines()[-40:]) if txt.strip() else "  (empty)")
    print("\nDONE")


main()
