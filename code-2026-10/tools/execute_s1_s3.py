"""S1+S3: Clean weixin from disabled profiles and restart gateways"""
import json, subprocess, os

profiles_to_clean = ["mybot", "qqbot2", "qqbot4"]
keep_weixin = ["qqbot3"]

print("=" * 50)
print("S1+S3: 清理禁用profile的weixin state")
print("=" * 50)

for p in profiles_to_clean:
    state_path = f"D:/hermes/hermes-data/profiles/{p}/gateway_state.json"
    if not os.path.exists(state_path):
        print(f"[{p}] ❌ No state file")
        continue
    
    with open(state_path) as f:
        d = json.load(f)
    
    removed_weixin = False
    if "platforms" in d:
        if "weixin" in d["platforms"]:
            del d["platforms"]["weixin"]
            removed_weixin = True
        # Also remove photon if present (already disabled)
        if "photon" in d["platforms"]:
            del d["platforms"]["photon"]
            removed_weixin = True
    
    if removed_weixin:
        with open(state_path, "w") as f:
            json.dump(d, f, indent=2)
        print(f"[{p}] ✅ Weixin/Photon removed from state")
    else:
        print(f"[{p}] ✅ Already clean")

print()
print("=" * 50)
print("重启gateways")
print("=" * 50)

for p in profiles_to_clean:
    try:
        r = subprocess.run(
            ["hermes", "--profile", p, "gateway", "stop"],
            capture_output=True, text=True, timeout=10
        )
        print(f"[{p}] Stop: {r.stdout[:40]}")
    except:
        pass

import time
time.sleep(3)

for p in profiles_to_clean:
    try:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        proc = subprocess.Popen(
            ["hermes", "--profile", p, "gateway", "run"],
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        )
        print(f"[{p}] ✅ Gateway restarted (PID={proc.pid})")
    except Exception as e:
        print(f"[{p}] ❌ Failed: {e}")

print()
print("✅ S1+S3 完成")
