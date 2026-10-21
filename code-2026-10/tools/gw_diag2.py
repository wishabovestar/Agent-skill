#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Full multi-profile gateway diagnosis.
Never prints credential VALUES -- only var names / lengths / hashes.
"""
import ctypes
import json
import os
import re
import subprocess
import sys
import datetime
import glob

ROOT = r"D:\hermes\hermes-data\profiles"
LOCKS = r"C:\Users\Administrator\.local\state\hermes\gateway-locks"
PROFS = ["mybot", "qqbot2", "qqbot3", "qqbot4", "qqbot5", "dong", "linshuo", "wenming"]

kernel32 = ctypes.windll.kernel32
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


def alive(pid):
    """Reliable liveness check -- does not depend on the process name."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    code = ctypes.c_ulong()
    ok = kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    kernel32.CloseHandle(h)
    return bool(ok) and code.value == STILL_ACTIVE


def ps(cmd):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                       capture_output=True)
    return r.stdout.decode("utf-8", "replace")


print("=" * 78)
print("GATEWAY DIAGNOSIS  " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("=" * 78)

# ---------------------------------------------------------------- 1. processes
print("\n### 1. LIVE GATEWAY PROCESSES (matched by command line)\n")
script = (
    "Get-CimInstance Win32_Process | "
    "Where-Object { $_.CommandLine -like '*gateway*' } | "
    "ForEach-Object { $_.ProcessId.ToString() + '|' + $_.Name + '|' + "
    "$_.CreationDate.ToString('MM-dd HH:mm:ss') + '|' + $_.CommandLine }"
)
out = ps(script)
found = []
for line in out.splitlines():
    line = line.strip()
    if "|" not in line:
        continue
    parts = line.split("|", 3)
    pid, name, ctime, cmdline = parts[0], parts[1], parts[2], parts[3] if len(parts) > 3 else ""
    prof = ""
    m = re.search(r"--profile\s+(\S+)", cmdline)
    if m:
        prof = m.group(1)
    else:
        m2 = re.search(r"profiles[\\/]+([A-Za-z0-9_]+)", cmdline)
        if m2:
            prof = m2.group(1)
    found.append((pid, name, ctime, prof, cmdline[:150]))
if found:
    for pid, name, ctime, prof, cmdline in found:
        print(f"  PID={pid:>7} {name:<18} start={ctime} profile={prof or '?':<9}")
        print(f"          {cmdline}")
else:
    print("  ** NONE -- no process with 'gateway' in its command line **")

# broader: any hermes-ish process at all
print("\n  -- any python*/hermes* process, for context --")
script2 = (
    "Get-Process | Where-Object { $_.ProcessName -match 'python|hermes|pythonw' } | "
    "ForEach-Object { $_.Id.ToString() + '|' + $_.ProcessName + '|' + $_.StartTime.ToString('MM-dd HH:mm:ss') }"
)
out2 = ps(script2)
cnt = 0
for line in out2.splitlines():
    line = line.strip()
    if "|" in line:
        cnt += 1
        if cnt <= 40:
            print("  " + line)
print(f"  (total {cnt})")

# ---------------------------------------------------------------- 2. locks
print("\n### 2. PLATFORM LOCKS -- holder PID liveness\n")
for f in sorted(glob.glob(os.path.join(LOCKS, "*.lock"))):
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception as e:
        print(f"  {os.path.basename(f)}: UNREADABLE ({e})")
        continue
    pid = d.get("pid")
    home = d.get("hermes_home", "")
    prof = os.path.basename(home) if home else "?"
    ok = alive(pid)
    flag = "ALIVE" if ok else "DEAD "
    print(f"  [{flag}] {d.get('scope','?'):<18} holder={prof:<9} pid={str(pid):<7} "
          f"updated={d.get('updated_at','?')[:19]}")
    if not ok:
        print(f"           ^ ORPHAN LOCK -- holder dead, this lock blocks everyone")

# ---------------------------------------------------------------- 3. state
print("\n### 3. gateway_state.json PER PROFILE\n")
for p in PROFS:
    sp = os.path.join(ROOT, p, "gateway_state.json")
    if not os.path.isfile(sp):
        print(f"  -- {p}: NO STATE FILE")
        continue
    try:
        d = json.load(open(sp, encoding="utf-8", errors="replace"))
    except Exception as e:
        print(f"  -- {p}: UNREADABLE ({e})")
        continue
    pid = d.get("pid")
    up = d.get("updated_at", "?")
    mins = "?"
    try:
        t = datetime.datetime.fromisoformat(str(up).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        mins = int((datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() // 60)
    except Exception:
        pass
    print(f"  -- {p}: pid={pid} alive={alive(pid)} gw={d.get('gateway_state')} "
          f"updated={str(up)[:19]} ({mins} min ago)")
    plats = d.get("platforms", {})
    if not plats:
        print("       platforms: (none)")
    for pn, info in plats.items():
        st = info.get("state")
        icon = "OK " if st == "connected" else "!! "
        print(f"       {icon}{pn:<10} {st:<14} code={info.get('error_code')} "
              f"msg={str(info.get('error_message'))[:100]}")

# ---------------------------------------------------------------- 4. config
print("\n### 4. CONFIG: which platforms each profile intends to run\n")
for p in PROFS:
    cfg = os.path.join(ROOT, p, "config.yaml")
    if not os.path.isfile(cfg):
        print(f"  -- {p}: no config.yaml")
        continue
    txt = open(cfg, encoding="utf-8", errors="replace").read()
    blk = ""
    m = re.search(r"^platforms:\s*$(.*?)(?=^\S|\Z)", txt, re.M | re.S)
    if m:
        ents = re.findall(r"^  ([a-z_]+):\s*$([\s\S]*?)(?=^  [a-z_]+:|\Z)", m.group(1), re.M)
        outl = []
        for pn, body in ents:
            en = re.search(r"enabled:\s*(true|false)", body)
            outl.append(f"{pn}={en.group(1) if en else '(no enabled key)'}")
        blk = ", ".join(outl) if outl else "(empty platforms block)"
    print(f"  -- {p}: {blk or '(no platforms block)'}")

# ---------------------------------------------------------------- 5. accounts dirs
print("\n### 5. weixin/accounts/ present? (auto-loads token and steals the lock)\n")
for p in PROFS:
    for cand in ("weixin/accounts", "weixin/accounts.disabled"):
        d = os.path.join(ROOT, p, cand)
        if os.path.isdir(d):
            files = os.listdir(d)
            print(f"  {p:<9} {cand:<26} {len(files)} file(s)")

print("\nDONE")
