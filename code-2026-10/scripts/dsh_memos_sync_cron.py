#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dsh_memos_sync_cron.py - cron wrapper around dsh_memos_ingest.py.

Runs the incremental dsh -> MemOS ingest and prints ONE line only when new rows
were actually written. Empty stdout means "nothing new", which Hermes cron's
--no-agent mode treats as silent (no message delivered).

Registered as:  hermes cron create 30m --script dsh_memos_sync_cron.py --no-agent
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INGEST = os.path.join(HERE, "dsh_memos_ingest.py")

def _pick_python() -> str:
    """Return an interpreter that can actually import the ingest's deps.

    Under Hermes cron this wrapper runs inside the runtime venv; under a shell
    it may run elsewhere. Probe candidates so a missing optional dep in one venv
    never silently breaks the sync.
    """
    candidates = [
        r"C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe",
        sys.executable,
    ]
    for cand in candidates:
        if not cand or not os.path.exists(cand):
            continue
        try:
            probe = subprocess.run(
                [cand, "-c", "import zstandard"],
                capture_output=True, timeout=60,
            )
            if probe.returncode == 0:
                return cand
        except Exception:
            continue
    return sys.executable


PY = _pick_python()


def main() -> int:
    try:
        proc = subprocess.run(
            [PY, INGEST],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        print("dsh→MemOS 同步超时(>600s)")
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print("dsh→MemOS 同步异常: %s" % exc)
        return 1

    out = (proc.stdout or "") + "\n" + (proc.stderr or "")

    if proc.returncode != 0:
        tail = "\n".join([ln for ln in out.splitlines() if ln.strip()][-4:])
        print("dsh→MemOS 同步失败 (exit=%d)\n%s" % (proc.returncode, tail))
        return 1

    m = re.search(r"rows inserted\s*=\s*(\d+)", out)
    inserted = int(m.group(1)) if m else 0

    if inserted > 0:
        print("dsh→MemOS 增量同步: +%d 条记录" % inserted)

    # Nothing new -> silent by design.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())