"""深度检查所有平台连接和消息收发能力"""
import json, subprocess, os, time
from datetime import datetime, timedelta

print("=" * 60)
print(f"全平台深度健康检查  {datetime.now().strftime('%H:%M:%S')}")
print("=" * 60)

profiles = ["mybot", "qqbot2", "qqbot3", "qqbot4"]
all_ok = True

for p in profiles:
    print(f"\n--- {p} ---")
    state_path = f"D:/hermes/hermes-data/profiles/{p}/gateway_state.json"
    log_path = f"D:/hermes/hermes-data/profiles/{p}/logs/gateway.log"
    
    if not os.path.exists(state_path):
        print(f"  ❌ 无state文件")
        all_ok = False
        continue
    
    with open(state_path) as f:
        state = json.load(f)
    
    pid = state.get("pid", 0)
    gs = state.get("gateway_state", "?")
    updated = state.get("updated_at", "")[:19]
    
    # Check 1: PID存活
    r = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], capture_output=True, timeout=5)
    alive = str(pid) in r.stdout.decode('gbk', errors='replace')
    
    if not alive:
        print(f"  ❌ PID={pid} 死亡 (state更新于 {updated})")
        all_ok = False
        continue
    
    # Check 2: state新鲜度（超过30分钟未更新视为可疑）
    age_hours = 999
    try:
        upd = datetime.fromisoformat(updated)
        age_hours = (datetime.now() - upd).total_seconds() / 3600
    except:
        pass
    
    freshness = "旧" if age_hours > 0.5 else "新"
    print(f"  ✅ PID={pid} alive state={gs} (更新于{updated}, {freshness})")
    
    # Check 3: 各平台state
    platforms = state.get("platforms", {})
    for name, info in platforms.items():
        s = info.get("state", "?")
        e = info.get("error_message", "")
        icon = {"connected": "✅", "disconnected": "❌", "retrying": "🔄"}.get(s, "❓")
        err = f"  err:{e[:50]}" if e else ""
        print(f"  {icon} {name}: {s} {err}")
        if s != "connected" and s not in ["disabled", "stopped"]:
            all_ok = False
    
    # Check 4: 日志中最近消息收发
    if os.path.exists(log_path):
        # inbound messages in last 10 min
        r = subprocess.run(
            ["grep", "inbound message", log_path],
            capture_output=True, text=True, timeout=5
        )
        lines = r.stdout.strip().split("\n")
        if lines and lines[0]:
            recent = [l for l in lines if l.startswith(f"2026-07-20 15:5") or l.startswith(f"2026-07-20 16:0")]
            if recent:
                for line in recent[-2:]:
                    msg = line[70:130] if len(line) > 70 else line
                    print(f"  📩 最近消息: {msg}")
            else:
                # Last message time
                last = lines[-1]
                ts = last[:19] if len(last) > 19 else "?"
                print(f"  📩 最后消息: {ts}")
        else:
            print(f"  📩 无消息记录")
        
        # Check if gateway is actively running (recent log lines)
        r2 = subprocess.run(["tail", "-1", log_path], capture_output=True, text=True, timeout=5)
        last_log = r2.stdout.strip()[:80]
        print(f"  📋 最后日志: {last_log}")
    
    # Check 5: Process memory (健康指标)
    r3 = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, timeout=5)
    txt = r3.stdout.decode('gbk', errors='replace')
    if str(pid) in txt:
        parts = txt.split()
        if len(parts) >= 5:
            mem = parts[-1].replace(',', '')
            if mem.isdigit():
                mem_mb = int(mem) // 1024
                flag = "✅" if mem_mb > 150 else "⚠️"
                print(f"  {flag} 内存占用: {mem_mb}MB")

# Check actual running gateways
print(f"\n--- 实际运行中的gateway进程 ---")
r4 = subprocess.run(
    ["tasklist"],
    capture_output=True, timeout=5
)
for line in r4.stdout.decode('gbk', errors='replace').split("\n")[3:]:
    parts = line.split()
    if len(parts) >= 5 and 'python' in parts[0].lower() and 'pythonw' not in parts[0].lower():
        mem = parts[-1].replace(',', '')
        if mem.isdigit() and int(mem) > 150000:
            pid = parts[1]
            mem_mb = int(mem) // 1024
            # Identify which profile
            profile_name = "?"
            for p in profiles:
                try:
                    with open(f"D:/hermes/hermes-data/profiles/{p}/gateway_state.json") as f:
                        sd = json.load(f)
                    if str(sd.get("pid")) == pid:
                        profile_name = p
                        break
                except: pass
            print(f"  PID={pid} {mem_mb}MB -> {profile_name}")

print(f"\n{'='*60}")
print(f"{'✅ 全部正常' if all_ok else '❌ 存在异常'}")
print(f"{'='*60}")
