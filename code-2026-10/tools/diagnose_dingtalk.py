"""Diagnose DingTalk connection"""
import json, subprocess

print("=" * 50)
print("钉钉连接诊断")
print("=" * 50)

# Read mybot state
with open("D:/hermes/hermes-data/profiles/mybot/gateway_state.json") as f:
    d = json.load(f)

pid = d.get("pid", 0)
r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, timeout=5)
alive = str(pid) in r.stdout.decode("gbk", errors="replace")

print(f"\nPID: {pid} | alive: {alive} | State: {d.get('gateway_state')}")
print(f"Updated: {str(d.get('updated_at','?'))[:19]}")

for name, info in d.get("platforms", {}).items():
    s = info.get("state", "?")
    e = info.get("error_message", "")
    print(f"  {name}: {s}", f"  err: {e[:80]}" if e else "")

# Check gateway log for DingTalk
print(f"\n--- 最近钉钉日志 ---")
log_path = "D:/hermes/hermes-data/profiles/mybot/logs/gateway.log"
try:
    r2 = subprocess.run(["grep", "-i", "dingtalk", log_path], capture_output=True, text=True, timeout=5)
    lines = r2.stdout.strip().split("\n")
    if lines and lines[0]:
        for line in lines[-5:]:
            print(f"  {line[:130]}")
    else:
        print("  (无钉钉活动)")
except:
    print("  (日志读取失败)")

# Check recent errors
print(f"\n--- 最近错误 ---")
try:
    r3 = subprocess.run(["tail", "-3", "D:/hermes/hermes-data/profiles/mybot/logs/errors.log"], capture_output=True, text=True, timeout=5)
    for line in r3.stdout.strip().split("\n"):
        if line.strip():
            print(f"  {line[:130]}")
except:
    print("  (无错误日志)")

print(f"\n--- 看门狗v3检测 ---")
r4 = subprocess.run(["python3", "D:/hermes/analysis/watchdog_v3.py"], capture_output=True, text=True, timeout=15)
for line in r4.stdout.strip().split("\n"):
    if "dingtalk" in line.lower() or "feishu" in line.lower() or "mybot" in line.lower():
        print(f"  {line}")
