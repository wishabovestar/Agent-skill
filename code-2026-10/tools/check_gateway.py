import json, os, subprocess

# Check gateway state
state_file = os.path.expanduser("~/AppData/Local/hermes/profiles/mybot/gateway_state.json")
if os.path.exists(state_file):
    with open(state_file) as f:
        d = json.load(f)
    print(f"Gateway PID: {d.get('pid', 'N/A')}")
    print(f"State: {d.get('gateway_state', 'N/A')}")
    print(f"Updated: {d.get('updated_at', 'N/A')}")
    for p, info in d.get('platforms', {}).items():
        s = info.get('state', '?')
        e = info.get('error_message', '')
        print(f"  {p}: {s}" + (f"  err={e}" if e else ""))
else:
    print("gateway_state.json not found")

# Check if gateway process is alive
if 'd' in dir() and d.get('pid', 0) > 0:
    pid = d['pid']
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True)
    out = r.stdout.decode("gbk", errors="replace")
    if str(pid) in out:
        print(f"\n✅ Gateway process {pid} IS running")
    else:
        print(f"\n❌ Gateway process {pid} NOT running (stale)")
    
    # Show memory/timestamp
    for line in out.split("\n"):
        if str(pid) in line:
            print(f"   {line.strip()}")

# Check for any Hermes processes
print("\n=== Any Hermes/Python gateway processes ===")
r = subprocess.run(["tasklist"], capture_output=True)
out = r.stdout.decode("gbk", errors="replace")
for line in out.split("\n"):
    if "hermes" in line.lower():
        print(line.strip())

# Check python processes with gateway relation
for line in out.split("\n"):
    if "python" in line.lower() and ("gate" in line.lower() or "hermes" in line.lower()):
        print(line.strip())
