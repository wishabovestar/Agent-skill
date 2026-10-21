#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Platform connectivity diagnosis across all Hermes profiles.
Prints NO credential values - only var names / lengths."""
import json, os, re, subprocess, sys, datetime, glob

ROOTS = [r"D:\hermes\hermes-data", r"C:\Users\Administrator\AppData\Local\hermes"]
PROF_DIRS = []
for r in ROOTS:
    p = os.path.join(r, "profiles")
    if os.path.isdir(p):
        for n in sorted(os.listdir(p)):
            if os.path.isdir(os.path.join(p, n)):
                PROF_DIRS.append((n, os.path.join(p, n)))
# de-dup by name, prefer D:
seen = {}
for n, p in PROF_DIRS:
    seen.setdefault(n, p)
PROF_DIRS = sorted(seen.items())

PLATFORM_VARS = ("WEIXIN_", "QQ_", "DINGTALK_", "FEISHU_", "TELEGRAM_", "DISCORD_", "PHOTON_")

def alive(pid):
    if not pid:
        return False
    try:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True)
        return str(pid) in r.stdout.decode("gbk", errors="replace")
    except Exception:
        return False

def read_env_names(path):
    names = []
    if not os.path.isfile(path):
        return names
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        m = re.match(r"^([A-Z_][A-Z0-9_]*)\s*=(.*)$", line)
        if m and m.group(1).startswith(PLATFORM_VARS):
            names.append((m.group(1), len(m.group(2).strip())))
    return names

print("=" * 78)
print("HERMES PLATFORM CONNECTIVITY DIAGNOSIS   " + str(datetime.datetime.now()))
print("=" * 78)

print("\n### 1. GATEWAY STATE PER PROFILE\n")
now = datetime.datetime.now(datetime.timezone.utc)
for name, pdir in PROF_DIRS:
    print(f"--- profile: {name}  ({pdir})")
    # .env platform vars
    envvars = read_env_names(os.path.join(pdir, ".env"))
    print("    .env platform vars: " + (", ".join(f"{k}(len={v})" for k, v in envvars) if envvars else "NONE"))
    # config platforms
    cfg = os.path.join(pdir, "config.yaml")
    if os.path.isfile(cfg):
        txt = open(cfg, encoding="utf-8", errors="replace").read()
        m = re.search(r"^platforms:\s*$(.*?)(?=^\S|\Z)", txt, re.M | re.S)
        if m:
            blk = m.group(1)
            ents = re.findall(r"^  ([a-z_]+):\s*$([\s\S]*?)(?=^  [a-z_]+:|\Z)", blk, re.M)
            out = []
            for pn, body in ents:
                en = re.search(r"enabled:\s*(true|false)", body)
                out.append(f"{pn}={en.group(1) if en else '?'}")
            print("    config platforms: " + (", ".join(out) if out else "(none)"))
    # gateway_state.json
    for cand in (os.path.join(pdir, "gateway_state.json"),):
        if os.path.isfile(cand):
            try:
                d = json.load(open(cand, encoding="utf-8", errors="replace"))
            except Exception as e:
                print(f"    state.json: UNREADABLE ({e})")
                continue
            pid = d.get("pid")
            upd = d.get("updated_at", "?")
            mins = None
            try:
                t = datetime.datetime.fromisoformat(upd.replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=datetime.timezone.utc)
                mins = int((now - t).total_seconds() // 60)
            except Exception:
                pass
            print(f"    pid={pid} alive={alive(pid)} gateway_state={d.get('gateway_state')} updated={upd} ({mins} min ago)" if mins is not None else f"    pid={pid} alive={alive(pid)} gateway_state={d.get('gateway_state')} updated={upd}")
            plats = d.get("platforms", {})
            if not plats:
                print("      platforms: (none recorded)")
            for pn, info in plats.items():
                st = info.get("state")
                icon = "OK " if st == "connected" else "!! "
                print(f"      {icon}{pn}: {st}  code={info.get('error_code')}  msg={str(info.get('error_message'))[:120]}")
        else:
            print("    state.json: MISSING")
    print()

print("### 2. RUNNING GATEWAY PROCESSES\n")
try:
    r = subprocess.run(["wmic", "process", "where", "name like '%python%'", "get", "ProcessId,CommandLine"],
                       capture_output=True)
    out = r.stdout.decode("gbk", errors="replace")
except Exception as e:
    out = f"(wmic failed: {e})"
for line in out.splitlines():
    if "gateway" in line and "profile" in line:
        print("  " + line.strip()[:200])
print()
print("DONE")
