"""Delayed, fail-safe restart of the host Hermes gateway (default-profile multiplexer).

Launched detached so it survives the gateway being killed.
Flow: sleep -> locate gateway pid (WMI cmdline match) -> taskkill /F -> wait ->
      spawn `hermes.exe gateway run --replace` detached -> wait -> verify -> log.

Fail-safe: if the old pid cannot be found or killed, nothing is started (avoids two
dispatchers racing on shared state).
Usage: pythonw restart_gateway_delayed.py [delay_seconds]
"""
import os
import subprocess
import sys
import time
import datetime
import json

HERMES_EXE = r"D:\hermes\hermes-data\bin\hermes.exe"
LOG = r"D:\hermes\analysis\logs\restart_gateway_delayed.log"
STATE = r"D:\hermes\hermes-data\profiles\default\gateway_state.json"
MATCH = "hermes_cli.main gateway run"


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def gateway_pids(min_age_s=120):
    """Live gateway dispatchers: python/pythonw whose cmdline runs `-m hermes_cli.main gateway run`
    and which are older than min_age_s (guards against transient helpers matching the text)."""
    ps = (
        "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*"
        + MATCH
        + "*' -and ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') } | "
        "ForEach-Object { [pscustomobject]@{pid=$_.ProcessId; name=$_.Name; "
        "age=[int]((Get-Date) - $_.CreationDate).TotalSeconds} } | ConvertTo-Json -Compress"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, timeout=60,
        )
        out = r.stdout.decode("utf-8", "replace").strip()
        if not out:
            return []
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        picks = [int(d["pid"]) for d in data if int(d.get("age") or 0) >= min_age_s]
        log(f"candidates={[(d.get('pid'), d.get('age')) for d in data]} picked={picks}")
        return picks
    except Exception as e:
        log(f"pid lookup failed: {e}")
        return []


def main():
    delay = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    log(f"--- scheduled restart in {delay}s (pid {os.getpid()}) ---")
    time.sleep(delay)

    pids = gateway_pids()
    state_pid = 0
    try:
        state_pid = int(json.load(open(STATE, encoding="utf-8")).get("pid") or 0)
    except Exception:
        pass
    log(f"found gateway pids={pids} state_pid={state_pid}")
    if not pids:
        log("ABORT: no gateway process matched; refusing to start a second dispatcher")
        return
    if state_pid and state_pid not in pids:
        log(f"note: state pid {state_pid} not in live set {pids} (state may be stale)")

    for pid in pids:
        r = subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=30)
        log(f"taskkill {pid} rc={r.returncode} out={r.stdout.decode('gbk','replace').strip()}")

    time.sleep(5)
    alive = gateway_pids()
    log(f"after kill live pids={alive}")
    if alive:
        log("ABORT: gateway still alive after taskkill; not starting a replacement")
        return

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    # Ensure the replacement gateway starts with the native dep dirs on PATH even if
    # this script inherited a stale environment (WMI/service parents often carry old PATH).
    extra = []
    gtk = r"D:\hermes\tools\gtk3\bin"
    if os.path.isdir(gtk):
        extra.append(gtk)
    winget = os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Microsoft\WinGet\Packages")
    if os.path.isdir(winget):
        for name in os.listdir(winget):
            if "FFmpeg" not in name:
                continue
            pkg = os.path.join(winget, name)
            try:
                for sub in os.listdir(pkg):
                    b = os.path.join(pkg, sub, "bin")
                    if os.path.isfile(os.path.join(b, "ffmpeg.exe")):
                        extra.append(b)
            except OSError:
                pass
    if extra:
        env["PATH"] = os.pathsep.join(extra) + os.pathsep + env.get("PATH", "")
    log(f"env PATH prefix={extra}")
    flags = (
        subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NEW_PROCESS_GROUP
        | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
    )
    out = open(r"D:\hermes\analysis\logs\restart_gateway_out.log", "a", encoding="utf-8")
    try:
        p = subprocess.Popen(
            [HERMES_EXE, "gateway", "run", "--replace"],
            env=env, creationflags=flags, cwd=r"D:\hermes",
            stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        )
        log(f"spawned replacement: pid={p.pid}")
    except Exception as e:
        log(f"START FAILED: {e}")
        return

    for i in range(6):
        time.sleep(10)
        # Verify by the pid we spawned + any live dispatcher, WITHOUT the age filter:
        # a just-started gateway is younger than min_age_s, which made the first run
        # report a false "no gateway pid" 60s after a successful restart.
        live = gateway_pids(min_age_s=0)
        rc = p.poll()
        log(f"t+{(i+1)*10}s spawned_pid={p.pid} poll={rc} live pids={live}")
        if rc is None and live:
            log("OK: gateway is back up")
            return
        if rc is not None:
            log(f"WARN: spawned gateway exited rc={rc} — manual start needed: "
                r'"D:\hermes\hermes-data\bin\hermes.exe" gateway run --replace')
            return
    log("WARN: spawned process alive but not matched by cmdline probe — check by hand")


if __name__ == "__main__":
    main()
