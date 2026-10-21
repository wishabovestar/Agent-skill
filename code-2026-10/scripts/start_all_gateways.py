"""Start all gateway profiles — for Windows Task Scheduler + watchdog"""
import subprocess, os, json

env = os.environ.copy()
env["PYTHONUTF8"] = "1"

profiles = ["mybot", "qqbot2", "qqbot3"]
for profile in profiles:
    # Check if already running by state.json
    state_file = f"D:/hermes/hermes-data/profiles/{profile}/gateway_state.json"
    try:
        with open(state_file) as f:
            state = json.load(f)
        pid = state.get("pid", 0)
        if pid > 0:
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, timeout=5)
            if str(pid) in r.stdout.decode("gbk", errors="replace"):
                print(f"[{profile}] Already running (PID {pid}), skipping")
                continue
    except:
        pass
    
    try:
        proc = subprocess.Popen(
            ["hermes", "--profile", profile, "gateway", "run", "--replace"],
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        )
        print(f"[{profile}] Started: PID={proc.pid}")
    except Exception as e:
        print(f"[{profile}] Failed: {e}")
