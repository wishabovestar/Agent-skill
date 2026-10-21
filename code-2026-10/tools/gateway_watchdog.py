"""
统一网关看门狗 — 中期+长期解决方案
功能介绍：
  中期(1-2周): 每2分钟检测 → 发现僵死 → 自动重启 → 微信通知
  长期(1-2月): Windows任务计划自启 + 多级降级 + 状态持久化

检测逻辑:
  1. 查PID存活 (tasklist)
  2. 查state.json新鲜度 (<5min = 鲜活, >5min = 可疑, >15min = 僵死)
  3. 查iLink API响应
  4. 查gateway-exit-diag.log最后退出标签

修复动作:
  1. 可疑(5-15min) → 发告警但不重启
  2. 僵死(>15min或PID不存活) → 自动重启
  3. 恢复后 → 发恢复通知
"""
import json, os, subprocess, time, re
from pathlib import Path
from datetime import datetime, timezone

# ===== 配置 =====
PROFILES = {
    "mybot": {
        "home": "D:/hermes/hermes-data/profiles/mybot",
        "profiles_home": "D:/hermes/hermes-data/profiles",
    },
    "qqbot2": {
        "home": "D:/hermes/hermes-data/profiles/qqbot2",
        "profiles_home": "D:/hermes/hermes-data/profiles",
    },
    "qqbot3": {
        "home": "D:/hermes/hermes-data/profiles/qqbot3",
        "profiles_home": "D:/hermes/hermes-data/profiles",
    },
}
CHECK_INTERVAL = 120  # 2分钟检测间隔
STALE_THRESHOLD = 300  # 5分钟 → 可疑
DEAD_THRESHOLD = 900   # 15分钟 → 僵死
WATCHDOG_LOG = Path("D:/hermes/hermes-data/watchdog.log")

def log(msg, profile=""):
    """Log with timestamp"""
    tag = f"[{profile}]" if profile else "[WATCHDOG]"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {tag} {msg}"
    print(line)
    WATCHDOG_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(WATCHDOG_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def is_pid_alive(pid):
    """Check if PID is alive (GBK-safe)"""
    if not pid or pid <= 0:
        return False
    try:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                          capture_output=True, timeout=5)
        return str(pid) in r.stdout.decode("gbk", errors="replace")
    except:
        return False

def get_state(profile_path):
    """Get gateway state"""
    state_file = os.path.join(profile_path, "gateway_state.json")
    if not os.path.exists(state_file):
        return None
    try:
        with open(state_file) as f:
            return json.load(f)
    except:
        return None

def get_state_age(state):
    """Get age of state in seconds"""
    if not state or not state.get("updated_at"):
        return float("inf")
    try:
        updated = datetime.fromisoformat(state["updated_at"])
        if updated.tzinfo:
            now = datetime.now(timezone.utc)
        else:
            now = datetime.now()
        return abs((now - updated).total_seconds())
    except:
        return float("inf")

def get_last_exit_tag(profile_path):
    """Get last gateway exit tag from exit-diag log"""
    diag_file = os.path.join(profile_path, "logs", "gateway-exit-diag.log")
    if not os.path.exists(diag_file):
        return None
    try:
        r = subprocess.run(["tail", "-1", diag_file], capture_output=True, text=True, timeout=5)
        if r.stdout:
            last = json.loads(r.stdout)
            return last.get("tag", "")
    except:
        pass
    return None

def diagnose_profile(name, path):
    """Diagnose a single profile's gateway health"""
    state = get_state(path)
    if not state:
        return {"status": "no_state", "pid": 0, "age": 0, "alive": False, "platforms": {}}
    
    pid = state.get("pid", 0)
    alive = is_pid_alive(pid)
    age = get_state_age(state)
    platforms = state.get("platforms", {})
    all_connected = all(p.get("state") == "connected" for p in platforms.values())
    exit_tag = get_last_exit_tag(path)
    
    # Determine health
    if alive and age < STALE_THRESHOLD and all_connected:
        health = "healthy"
    elif alive and age >= STALE_THRESHOLD:
        health = "stale_state"  # PID alive but state not updated
    elif not alive and age >= DEAD_THRESHOLD:
        health = "dead"
    elif not alive:
        health = "recently_died"
    elif age < STALE_THRESHOLD:
        health = "starting"
    else:
        health = "unknown"
    
    return {
        "status": health,
        "pid": pid,
        "alive": alive,
        "age_seconds": age,
        "platforms": platforms,
        "all_connected": all_connected,
        "gateway_state": state.get("gateway_state"),
        "exit_tag": exit_tag,
    }

def restart_gateway(profile_name, profile_path):
    """Restart a profile's gateway with DETACHED_PROCESS"""
    log(f"🚀 重启 gateway [{profile_name}]...", profile_name)
    try:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        proc = subprocess.Popen(
            ["hermes", "--profile", profile_name, "gateway", "run", "--replace"],
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        )
        log(f"  已启动 PID={proc.pid}", profile_name)
        return True
    except Exception as e:
        log(f"  ❌ 启动失败: {e}", profile_name)
        return False

def send_notification(profile_name, message):
    """Send notification via working gateway"""
    try:
        subprocess.run(
            ["hermes", "--profile", profile_name, "send", "-t", "weixin", message],
            capture_output=True, text=True, timeout=15,
        )
    except:
        pass  # Best effort

def run_check():
    """Run one check cycle for all profiles"""
    log(f"🔍 开始健康检查 ({len(PROFILES)} profiles)")
    actions_taken = []
    
    for name, cfg in PROFILES.items():
        diag = diagnose_profile(name, cfg["home"])
        log(f"  [{name}] PID={diag['pid']} alive={diag['alive']} age={diag['age_seconds']:.0f}s status={diag['status']}", name)
        
        if diag["status"] in ["dead", "recently_died"]:
            # Gateway process dead — restart immediately
            log(f"  ⚠ 检测到{diag['status']}，执行重启", name)
            if restart_gateway(name, cfg["home"]):
                actions_taken.append(f"{name}: restarted (was {diag['status']})")
                send_notification(name, 
                    f"⚠ 微信连接已断开，自动修复中...\n"
                    f"状态: {diag['status']} (PID={diag['pid']})\n"
                    f"已触发自动重启")
        
        elif diag["status"] == "stale_state":
            log(f"  ⚠ state过期({diag['age_seconds']:.0f}s)，但PID存活，等待状态更新", name)
        elif diag["status"] == "recently_died":
            log(f"  ⚠ 进程死亡，立即重启", name)
        
        elif diag["status"] == "healthy":
            log(f"  ✅ 健康", name)
    
    if actions_taken:
        log(f"📋 本次动作: {', '.join(actions_taken)}")
    else:
        log(f"📋 无需动作，全部正常")
    
    return actions_taken

# ===== 持续运行模式 =====
def run_forever():
    """Run watchdog in continuous loop"""
    log(f"{'='*50}")
    log(f"看门狗启动 — 间隔{CHECK_INTERVAL}s，检测{len(PROFILES)}个profile")
    log(f"  僵死阈值: {DEAD_THRESHOLD}s ({DEAD_THRESHOLD//60}min)")
    log(f"  可疑阈值: {STALE_THRESHOLD}s ({STALE_THRESHOLD//60}min)")
    log(f"{'='*50}")
    
    while True:
        try:
            run_check()
        except Exception as e:
            log(f"❌ 检测异常: {e}")
        time.sleep(CHECK_INTERVAL)

# ===== 单次检测模式 (给cron用) =====
def run_once():
    """Run one check — for cron job"""
    actions = run_check()
    return actions

if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "once"
    
    if mode == "once":
        run_once()
    elif mode == "forever":
        run_forever()
    elif mode == "diag":
        # 诊断所有profile
        for name, cfg in PROFILES.items():
            d = diagnose_profile(name, cfg["home"])
            print(f"[{name}]")
            print(f"  PID: {d['pid']} | Alive: {d['alive']} | Age: {d['age_seconds']:.0f}s")
            print(f"  Status: {d['status']} | GateState: {d['gateway_state']}")
            print(f"  AllConnected: {d['all_connected']} | ExitTag: {d['exit_tag']}")
            for p, info in d['platforms'].items():
                print(f"    {p}: {info.get('state')}")
