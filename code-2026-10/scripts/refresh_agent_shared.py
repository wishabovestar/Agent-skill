"""Cron shim -- refresh the Hermes <-> DSH shared plane (D:/agent-shared).

WHY .py: the scheduler runs a `.sh` through bash, which eats the backslashes in a Windows
path ("D:hermeshermes-...") => exit 127. A `.py` script runs on the scheduler's own
interpreter, so there is no path/quoting hazard.

SINGLE SOURCE OF TRUTH is the bridge itself -- this file only relays, so no logic is
duplicated here (the gateway-watchdog skill warns about dual-copy drift).

WATCHDOG PATTERN: quiet when everything works (a one-line heartbeat), verbose + non-zero
only when a step fails, so the cron alert fires exactly when it should.
"""
import subprocess
import sys

BRIDGE = r"D:/agent-shared/bin/agent_bridge.py"
PY = sys.executable

for step in ("export", "ingest-dsh", "verify"):
    proc = subprocess.run([PY, BRIDGE, step], capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        print(f"❌ 共享面刷新失败于 `{step}` (exit {proc.returncode})")
        print(proc.stdout or "")
        print(proc.stderr or "")
        sys.exit(1)

# 静默成功：stdout 留空 ⇒ 调度器不发任何通知（与既有的补丁校验/看门狗 cron 一致）。
# 只有上面失败分支才有输出，届时才会推送告警。要看它是否在跑：`hermes cron list` 的 Last run。

