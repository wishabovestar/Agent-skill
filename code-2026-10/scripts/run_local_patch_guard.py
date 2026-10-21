"""Cron shim -- verify this machine's LOCAL (non-upstream) patches are still applied.

WHY .py AND NOT .sh
    The scheduler runs a `.sh` through bash, which needs `python` to resolve on the cron
    environment's PATH -- it does NOT, and the job died with exit 127 (command not found).
    A `.py` script is executed by the scheduler's OWN interpreter, so there is no PATH
    dependency at all. That is the robust choice for a no_agent cron.

SINGLE SOURCE OF TRUTH lives in analysis/ -- this file only relays, so the logic exists in
exactly one place (the gateway-watchdog skill warns about dual-copy drift).

WATCHDOG PATTERN
    --quiet prints NOTHING while every patch is present, so the scheduler sends nothing.
    A missing patch prints a report AND exits non-zero => the alert is delivered.
"""
import runpy
import sys

GUARD = r'D:/hermes/analysis/local_patch_guard.py'

sys.argv = [GUARD, '--quiet']
runpy.run_path(GUARD, run_name='__main__')
