#!/usr/bin/env python3
"""flicker_tick.py -- Hermes cron wrapper (profile scripts dir).

Runs the PowerShell flicker watchdog at D:\\hermes\\analysis\\flicker_watchdog.ps1.
Kept silent (empty stdout) unless the watchdog itself reports something, so it is
safe to use with no_agent=True.
"""
import subprocess
import sys

PS1 = r"D:\hermes\analysis\flicker_watchdog.ps1"

try:
    p = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PS1],
        capture_output=True, text=True, timeout=120,
    )
    out = (p.stdout or "").strip()
    if out:
        print(out)
    if p.returncode != 0:
        print(f"[flicker_tick] watchdog exit={p.returncode} stderr={(p.stderr or '').strip()[:500]}", file=sys.stderr)
except Exception as exc:  # noqa: BLE001
    print(f"[flicker_tick] failed to run watchdog: {exc}", file=sys.stderr)
    sys.exit(1)
