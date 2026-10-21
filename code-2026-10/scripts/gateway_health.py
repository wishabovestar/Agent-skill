#!/usr/bin/env python3
"""Gateway进程存活监控 - 每5分钟检查，异常自动重启
静默模式: 正常无输出，异常时输出告警+尝试自愈

检测: mybot和qqbot2两个gateway
"""
import json, os, sys, time, subprocess

PROFILES = [
    {"name": "mybot", "home": "D:\\hermes\\hermes-data\\profiles\\mybot"},
    {"name": "qqbot2", "home": "D:\\hermes\\hermes-data\\profiles\\qqbot2"},
]
ALERTS = []

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def check_profile(profile):
    name = profile["name"]
    home = profile["home"]
    STATE = os.path.join(home, "gateway_state.json")
    
    # 1. 读state
    if not os.path.exists(STATE):
        ALERTS.append(f"[{name}] state文件不存在")
        return False
    try:
        with open(STATE) as f:
            state = json.load(f)
    except Exception as e:
        ALERTS.append(f"[{name}] state读取失败: {e}")
        return False
    
    pid = state.get("pid")
    gs = state.get("gateway_state")
    
    # 2. state文件时间
    age = time.time() - os.path.getmtime(STATE)
    if age > 300:  # 5分钟未更新
        ALERTS.append(f"[{name}] state已{age/60:.0f}分钟未更新")
    
    # 3. PID存活
    if not pid:
        ALERTS.append(f"[{name}] state中无PID")
        return False
    
    try:
        import psutil
        p = psutil.Process(pid)
        alive = p.is_running() and p.status() != psutil.STATUS_ZOMBIE
        if not alive:
            ALERTS.append(f"[{name}] PID {pid} 已死")
            return False
    except (psutil.NoSuchProcess, ImportError):
        ALERTS.append(f"[{name}] PID {pid} 不存在")
        return False
    
    # 4. 平台状态
    platforms = state.get("platforms", {})
    for plat, info in platforms.items():
        if info.get("state") != "connected":
            ALERTS.append(f"[{name}] {plat}: {info.get('state')}")
    
    return True

def restart_gateway(name):
    log(f"🔄 尝试重启 {name} gateway...")
    hermes = os.path.join(os.path.dirname(sys.executable), "hermes")
    if not os.path.exists(hermes + ".exe"):
        hermes = os.path.join(
            "C:\\Users\\Administrator\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\hermes.exe"
        )
    try:
        subprocess.run(
            [hermes, "--profile", name, "gateway", "run", "--replace"],
            capture_output=True, text=True, timeout=30
        )
        log(f"✅ {name} gateway已启动")
        return True
    except subprocess.TimeoutExpired:
        log(f"⏱ {name} gateway启动超时")
        return False
    except Exception as e:
        log(f"❌ {name} gateway启动失败: {e}")
        return False

def main():
    mybot_ok = check_profile(PROFILES[0])
    qqbot2_ok = check_profile(PROFILES[1])
    
    if mybot_ok and qqbot2_ok:
        return  # 全部正常，静默
    
    log("⚠️ Gateway健康异常")
    for a in ALERTS:
        log(f"  {a}")
    
    # 自愈
    if not mybot_ok:
        restart_gateway("mybot")
    if not qqbot2_ok:
        restart_gateway("qqbot2")
    time.sleep(5)
    
    # 二次检查
    if check_profile(PROFILES[0]):
        log("✅ mybot 自愈成功")
    else:
        log("❌ mybot 自愈失败")
    if check_profile(PROFILES[1]):
        log("✅ qqbot2 自愈成功")
    else:
        log("❌ qqbot2 自愈失败")

if __name__ == "__main__":
    main()
