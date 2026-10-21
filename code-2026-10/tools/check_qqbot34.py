"""Check qqbot3 and qqbot4 gateway status"""
import json, subprocess

for p in ["qqbot3", "qqbot4"]:
    print(f"\n=== {p} ===")
    try:
        with open(f"D:/hermes/hermes-data/profiles/{p}/gateway_state.json") as f:
            d = json.load(f)
        pid = d.get("pid", 0)
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, timeout=5)
        alive = str(pid) in r.stdout.decode("gbk", errors="replace")
        print(f"  PID: {pid} | alive: {alive} | State: {d.get('gateway_state')}")
        updated = d.get("updated_at", "?")
        if len(updated) > 19:
            updated = updated[:19]
        print(f"  Updated: {updated}")
        for name, info in d.get("platforms", {}).items():
            s = info.get("state", "?")
            e = info.get("error_message")
            print(f"    {name}: {s}" + (f"  err: {e}" if e else ""))
    except FileNotFoundError:
        print(f"  ❌ No gateway_state.json")
    except Exception as ex:
        print(f"  ❌ {ex}")
    
    # Check .env
    print(f"  .env exists: {os.path.exists(f'D:/hermes/hermes-data/profiles/{p}/.env')}")
    if os.path.exists(f"D:/hermes/hermes-data/profiles/{p}/.env"):
        with open(f"D:/hermes/hermes-data/profiles/{p}/.env") as f:
            env = f.read()
        for kw in ["WEIXIN_TOKEN", "WEIXIN_ACCOUNT", "QQ_APP_ID"]:
            for line in env.split("\n"):
                if line.startswith(kw):
                    val = line.split("=", 1)[1][:20]
                    print(f"    {kw}={val}...")
    
    # Check gateway process exclusing state pid
    print(f"  Hermes python processes:")
    r2 = subprocess.run(["tasklist"], capture_output=True, timeout=5)
    for line in r2.stdout.decode("gbk", errors="replace").split("\n"):
        if "python" in line.lower() and "Hermes" not in line:
            parts = line.split()
            if len(parts) > 1 and parts[1].isdigit():
                ppid = int(parts[1])
                if ppid != 0 and str(ppid) != str(pid):
                    pass  # Other python processes
