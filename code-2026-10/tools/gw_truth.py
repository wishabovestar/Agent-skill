#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GROUND TRUTH report for the Hermes gateway fleet.

Writes everything with explicit Windows paths (no MSYS path translation games)
and correlates: command-line presence -> state.json -> lock files -> config.
"""
import ctypes
import datetime
import glob
import json
import os
import re
import subprocess

ROOT = r"D:\hermes\hermes-data\profiles"
LOCKS = os.path.join(os.environ.get("USERPROFILE", r"C:\Users\Administrator"),
                     ".local", "state", "hermes", "gateway-locks")
PROFS = ["mybot", "qqbot2", "qqbot3", "qqbot4", "qqbot5", "dong", "wenming", "linshuo"]

kernel32 = ctypes.windll.kernel32


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
    c = ctypes.c_ulong()
    ok = kernel32.GetExitCodeProcess(h, ctypes.byref(c))
    kernel32.CloseHandle(h)
    return bool(ok) and c.value == 259


def ps(cmd):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True)
    for enc in ("utf-8", "gbk"):
        try:
            return r.stdout.decode(enc)
        except Exception:
            continue
    return r.stdout.decode("utf-8", "replace")


print("=" * 78)
print("GROUND TRUTH  " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("=" * 78)

# ---- command lines of every live hermes/python process ----
out = ps("Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|hermes' } | "
         "ForEach-Object { $_.ProcessId.ToString() + '@@' + $_.CommandLine }")
live = []
for line in out.splitlines():
    if "@@" not in line:
        continue
    pid, _, cl = line.partition("@@")
    if not cl.strip():
        continue
    m = re.search(r"--profile\s+(\S+)", cl)
    if m and "gateway" in cl:
        live.append((int(pid), m.group(1), cl.strip()))
print(f"\n### live gateway processes: {len(live)}")
for pid, prof, cl in sorted(live, key=lambda x: x[1]):
    print(f"  {prof:<9} pid={pid:<7} {cl[:110]}")

print("\n### per-profile truth")
print(f"  {'profile':<9} {'state.pid':>9} {'alive':>5} {'gw_state':<9} {'proc?':<6} {'config platforms':<34} {'state platforms'}")
for p in PROFS:
    sp = os.path.join(ROOT, p, "gateway_state.json")
    d = {}
    if os.path.isfile(sp):
        try:
            d = json.load(open(sp, encoding="utf-8", errors="replace"))
        except Exception as e:
            d = {"_err": str(e)}
    pid = d.get("pid")
    home = os.path.basename(str(d.get("hermes_home", "?")))
    proc = any(x[1] == p for x in live)

    cfgtxt = ""
    cfg = os.path.join(ROOT, p, "config.yaml")
    if os.path.isfile(cfg):
        txt = open(cfg, encoding="utf-8", errors="replace").read()
        m = re.search(r"^platforms:\s*$(.*?)(?=^\S|\Z)", txt, re.M | re.S)
        if m:
            ents = re.findall(r"^  ([a-z_]+):\s*$([\s\S]*?)(?=^  [a-z_]+:|\Z)", m.group(1), re.M)
            pairs = []
            for pn, body in ents:
                en = re.search(r"enabled:\s*(true|false)", body)
                pairs.append(pn + "=" + (en.group(1) if en else "y"))
            cfgtxt = ",".join(pairs)
    stp = ",".join(f"{k}={v.get('state')}" for k, v in d.get("platforms", {}).items())
    print(f"  {p:<9} {str(pid):>9} {str(alive(pid)):>5} {str(d.get('gateway_state')):<9} "
          f"{str(proc):<6} {cfgtxt:<34} {stp}")

print("\n### locks")
for f in sorted(glob.glob(os.path.join(LOCKS, "*.lock"))):
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    h = os.path.basename(str(d.get("hermes_home", "?")))
    print(f"  {d.get('scope','?'):<18} {h:<9} pid={str(d.get('pid')):<7} alive={alive(d.get('pid'))}")

print("\n### weixin/accounts state (a non-carrier with accounts/ steals the lock)")
for p in PROFS:
    for sub in ("weixin/accounts", "weixin/accounts.disabled"):
        parts = sub.split("/")
        d = os.path.join(ROOT, p, *parts)
        if os.path.isdir(d):
            print(f"  {p:<9} {sub:<24} {len(os.listdir(d))} file(s)")

print("\n### state.db sizes (drives post-crash startup time)")
for p in PROFS:
    f = os.path.join(ROOT, p, "state.db")
    if os.path.isfile(f):
        sz = os.path.getsize(f)
        est = sz / 1e9 * 72  # measured ~72 s/GB for PRAGMA quick_check(1)
        print(f"  {p:<9} {sz/1e6:>9.1f} MB   est. quick_check after unclean exit ~{est:.0f}s")
print("\nDONE")
