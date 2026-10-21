"""Show all gateway profiles status"""
import json, subprocess

profiles = ["mybot", "qqbot2", "qqbot3"]
print("=== 三profile最终状态 ===")
print()
for p in profiles:
    try:
        with open(f"D:/hermes/hermes-data/profiles/{p}/gateway_state.json") as f:
            d = json.load(f)
        pid = d.get("pid", 0)
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, timeout=5)
        alive = str(pid) in r.stdout.decode("gbk", errors="replace")
        plats = " ".join(f"{k}:{v.get('state','?')}" for k, v in d.get("platforms", {}).items())
        print(f"  {p:8s} PID={pid:<6} alive={str(alive):5}  {plats}")
    except Exception as e:
        print(f"  {p:8s} ERROR: {e}")
