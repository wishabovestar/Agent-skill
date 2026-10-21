"""Diagnose all profiles: gateway state, iLink test, watchdog status"""
import json, subprocess, os

profiles = ["mybot", "qqbot2", "qqbot3", "qqbot4"]

print("=" * 55)
print("全平台状态诊断")
print("=" * 55)

for p in profiles:
    print(f"\n--- {p} ---")
    state_file = f"D:/hermes/hermes-data/profiles/{p}/gateway_state.json"
    if not os.path.exists(state_file):
        print(f"  无 gateway_state.json")
        continue
    
    with open(state_file) as f:
        d = json.load(f)
    
    pid = d.get("pid", 0)
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, timeout=5)
    alive = str(pid) in r.stdout.decode("gbk", errors="replace")
    
    print(f"  PID: {pid} | alive: {alive} | State: {d.get('gateway_state')}")
    print(f"  Updated: {str(d.get('updated_at','?'))[:19]}")
    
    platforms = d.get("platforms", {})
    for name, info in platforms.items():
        s = info.get("state", "?")
        e = info.get("error_message")
        print(f"    {name}: {s}" + (f"  err: {e}" if e else ""))
    
    # iLink direct test
    env_path = f"D:/hermes/hermes-data/profiles/{p}/.env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("WEIXIN_TOKEN="):
                    tok = line.strip().split("=", 1)[1]
                    try:
                        rr = subprocess.run(
                            ["curl", "-s", "--max-time", "8",
                             "-H", f"Authorization: Bearer {token}",
                             "-H", "Content-Type: application/json",
                             "-d", '{"get_updates_buf":""}',
                             "https://ilinkai.weixin.qq.com/ilink/bot/getupdates"],
                            capture_output=True, timeout=10
                        )
                        resp = rr.stdout.decode(errors="replace").strip()[:80]
                        print(f"  iLink: {resp}")
                    except Exception as ex:
                        print(f"  iLink: error {ex}")
                    break
        if not any("WEIXIN_TOKEN" in line for line in open(env_path)):
            print(f"  iLink: 无WEIXIN_TOKEN")

# Check watchdogs
print("\n" + "=" * 55)
print("看门狗/监控状态")
print("=" * 55)
r = subprocess.run(["cronjob", "list"], capture_output=True, timeout=10)
out = r.stdout.decode(errors="replace")
for keyword in ["看门狗", "watchdog", "weixin_hb", "weixin_recovery", "微信心跳"]:
    for line in out.split("\n"):
        if keyword.lower() in line.lower():
            print(f"  {line.strip()[:120]}")

# Summary
print("\n" + "=" * 55)
print("存在问题汇总")
print("=" * 55)
for p in profiles:
    state_file = f"D:/hermes/hermes-data/profiles/{p}/gateway_state.json"
    if not os.path.exists(state_file):
        print(f"  ❌ {p}: 无状态文件")
        continue
    with open(state_file) as f:
        d = json.load(f)
    pid = d.get("pid", 0)
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, timeout=5)
    alive = str(pid) in r.stdout.decode("gbk", errors="replace")
    if not alive:
        print(f"  ❌ {p}: PID {pid} 已死 (state过期)")
    else:
        problems = []
        for name, info in d.get("platforms", {}).items():
            if info.get("state") != "connected":
                problems.append(f"{name}:{info.get('state')}")
        if problems:
            print(f"  ⚠ {p}: {', '.join(problems)}")
        else:
            print(f"  ✅ {p}: 正常")
