"""收集所有profile的崩溃统计和日志分析"""
import json, subprocess, os, re
from datetime import datetime, timedelta

print("=" * 60)
print("全平台连接稳定性数据采集")
print("=" * 60)

# 1. Gateway exit diagnostics
print("\n--- 1. Gateway启动/退出记录 ---")
for p in ['mybot', 'qqbot2', 'qqbot3', 'qqbot4']:
    log = f"D:/hermes/hermes-data/profiles/{p}/logs/gateway-exit-diag.log"
    if os.path.exists(log):
        r = subprocess.run(["tail", "-20", log], capture_output=True, text=True, timeout=5)
        starts = [l for l in r.stdout.split("\n") if 'gateway.start' in l]
        print(f"  {p}: {len(starts)} 次启动记录")
        for s in starts[-5:]:
            try:
                d = json.loads(s)
                pid = d.get('pid','?')
                ts = d.get('ts','')[:19]
                print(f"    PID={pid} ts={ts}")
            except: pass
    else:
        print(f"  {p}: 无日志")

# 2. Error log analysis
print("\n--- 2. 错误日志分析 ---")
for p in ['mybot', 'qqbot2', 'qqbot3', 'qqbot4']:
    elog = f"D:/hermes/hermes-data/profiles/{p}/logs/errors.log"
    glog = f"D:/hermes/hermes-data/profiles/{p}/logs/gateway.log"
    if os.path.exists(glog):
        # Count crash types
        r = subprocess.run(["grep", "-i", "readerthread|UnicodeDecodeError|crash|exception|traceback", glog],
                          capture_output=True, text=True, timeout=5)
        crashes = len(r.stdout.strip().split("\n")) if r.stdout.strip() else 0
        print(f"  {p}: {crashes} crash/exception 相关日志")

# 3. Current state
print("\n--- 3. 当前状态 ---")
for p in ['mybot', 'qqbot2', 'qqbot3', 'qqbot4']:
    try:
        with open(f"D:/hermes/hermes-data/profiles/{p}/gateway_state.json") as f:
            d = json.load(f)
        pid = d.get('pid', 0)
        r = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], capture_output=True, timeout=5)
        alive = str(pid) in r.stdout.decode('gbk', errors='replace')
        plats = ' '.join(f'{k}:{v["state"]}' for k,v in d.get('platforms',{}).items())
        updated = d.get('updated_at', '')[:19]
        print(f"  {p:8s} PID={pid:<6} alive={str(alive):5} {plats} (updated={updated})")
        if not alive:
            # Check if watchdog marked it
            for k,v in d.get('platforms',{}).items():
                if v.get('error_message','') and '看门狗' in v.get('error_message',''):
                    print(f"           ⚠ 看门狗标记: {v['error_message'][:50]}")
    except: pass

# 4. Watchdog status
print("\n--- 4. 看门狗状态 ---")
for f in ['D:/hermes/hermes-data/watchdog_v3.log', 'D:/hermes/hermes-data/watchdog_restarts.json']:
    if os.path.exists(f):
        size = os.path.getsize(f)
        print(f"  ✅ {os.path.basename(f)} ({size//1024}KB)")
        if 'restarts' in f:
            with open(f) as ff:
                d = json.load(ff)
            for p,ts in d.items():
                if ts:
                    print(f"     {p}: {len(ts)}次重启")
    else:
        print(f"  ❌ {os.path.basename(f)} 不存在")

# 5. PYTHONUTF8 setting
print("\n--- 5. PYTHONUTF8 环境变量 ---")
r = subprocess.run(["python", "-c", "import os; print(os.environ.get('PYTHONUTF8','NOT SET'))"], capture_output=True, text=True, timeout=5)
print(f"  当前shell: PYTHONUTF8={r.stdout.strip()}")

# Check in .bashrc
if os.path.exists(os.path.expanduser("~/.bashrc")):
    r = subprocess.run(["grep", "PYTHONUTF8", os.path.expanduser("~/.bashrc")], capture_output=True, text=True, timeout=5)
    print(f"  .bashrc: {'✅ set' if r.stdout.strip() else '❌ NOT SET'}")

print("\n--- 采集完成 ---")
