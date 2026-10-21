"""Start gateway for a given profile in DETACHED_PROCESS mode"""
import subprocess, os, sys, time, json

profile = sys.argv[1]
HOME = f"D:/hermes/hermes-data/profiles/{profile}"
VENV_DIR = os.path.expanduser("~/AppData/Local/hermes/hermes-agent/venv")
HERMES_EXE = os.path.join(VENV_DIR, "Scripts", "hermes.exe")
if not os.path.exists(HERMES_EXE):
    HERMES_EXE = os.path.join(VENV_DIR, "Scripts", "hermes")

DETACHED = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

# Step 1: Clean stale state
state_file = os.path.join(HOME, "gateway_state.json")
state_file_bak = state_file + ".bak"
pid_file = os.path.join(HOME, "gateway.pid")
lock_file = os.path.join(HOME, "gateway.lock")

if os.path.exists(state_file):
    if os.path.exists(state_file_bak):
        os.remove(state_file_bak)
    os.rename(state_file, state_file_bak)
    log(f"Backed up stale state: {state_file} -> {state_file_bak}")
for f in [pid_file, lock_file]:
    if os.path.exists(f):
        os.remove(f)
        log(f"Removed stale file: {f}")

# Step 2: Start gateway detached
log(f"Starting gateway for profile '{profile}'...")
p = subprocess.Popen(
    [HERMES_EXE, "--profile", profile, "gateway", "run"],
    env={**os.environ, "HERMES_GATEWAY_DETACHED": "1"},
    creationflags=DETACHED,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    stdin=subprocess.DEVNULL,
)
log(f"Gateway started (PID {p.pid})")

# Step 3: Wait and verify
time.sleep(5)
# Check if gateway_state.json appeared
if os.path.exists(state_file):
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            s = json.load(f)
        log(f"State file updated: pid={s.get('pid')}, state={s.get('gateway_state')}")
        # Also check Windows tasklist
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {s.get('pid')}", "/NH"],
            capture_output=True, text=True, timeout=5
        )
        if str(s.get('pid')) in r.stdout:
            log(f"✅ PID {s.get('pid')} confirmed alive via tasklist")
        else:
            log(f"⚠ PID {s.get('pid')} NOT found in tasklist — may have crashed immediately")
    except Exception as e:
        log(f"⚠ Could not read state file: {e}")
else:
    log(f"⚠ state file not created yet — checking again...")
    time.sleep(5)
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as f:
            s = json.load(f)
        log(f"State file (after delay): pid={s.get('pid')}")
    else:
        log("❌ State file still missing after 10s — gateway likely failed to start")

log("Done")
