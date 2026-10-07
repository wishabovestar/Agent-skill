"""Start all gateway profiles — for Windows Task Scheduler + watchdog"""
import subprocess, os, json

env = os.environ.copy()
env["PYTHONUTF8"] = "1"

profiles = ["mybot", "qqbot3"]  # qqbot2 is retired (migrated to qqbot3)
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
        proc_env = env.copy()
        # mybot的weixin已禁用 — 清除全局WEIXIN env vars防止启动时抢token
        if profile == "mybot":
            for k in list(proc_env.keys()):
                if k.startswith("WEIXIN_"):
                    del proc_env[k]
            proc_env["WEIXIN_ENABLED"] = "false"
        proc = subprocess.Popen(
            # Use the 3.14 launcher shim explicitly. Bare \"hermes\" resolves to the
            # 3.11 venv on PATH, but the install environment ships a cp314-built
            # pydantic_core -> ModuleNotFoundError -> hosted_room_worker crash loop.
            # (2026-10-07)  D:\\hermes\\hermes-data\\bin\\hermes.exe self-selects python-3.14.7.
            [r"D:\hermes\hermes-data\bin\hermes.exe", "--profile", profile, "gateway", "run", "--replace"],
            env=proc_env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        )
        print(f"[{profile}] Started: PID={proc.pid}")
    except Exception as e:
        print(f"[{profile}] Failed: {e}")
