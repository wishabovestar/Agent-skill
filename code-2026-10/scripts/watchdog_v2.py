"""
增强版看门狗 v2 — iLink直达检测 + State真实化 + Token有效期追踪
"""
import json, subprocess, os, time, re
from pathlib import Path
from datetime import datetime

LOG = Path("D:/hermes/hermes-data/watchdog_v2.log")
ILINK_URL = "https://ilinkai.weixin.qq.com/ilink/bot/getupdates"
TOKEN_LIFETIME = 6 * 3600  # 6小时Token有效期预警

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {msg}"
    print(line)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def check_pid(pid):
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, timeout=5)
    return str(pid) in r.stdout.decode("gbk", errors="replace")

def get_token_age(profile):
    """估算Token使用时长"""
    env_path = f"D:/hermes/hermes-data/profiles/{profile}/.env"
    if not os.path.exists(env_path):
        return None
    with open(env_path) as f:
        for line in f:
            if line.startswith("WEIXIN_TOKEN="):
                tok = line.split("=", 1)[1].strip()
                # Try to guess age from token pattern (not reliable)
                return len(tok)  # placeholder
    return None

def test_ilink(profile):
    """直接测试iLink API"""
    env_path = f"D:/hermes/hermes-data/profiles/{profile}/.env"
    if not os.path.exists(env_path):
        return None, "no_env"
    with open(env_path) as f:
        token = None
        for line in f:
            if line.startswith("WEIXIN_TOKEN=") and not line.startswith("#WEIXIN_TOKEN="):
                token = line.split("=", 1)[1].strip()
                break
    if not token:
        return None, "no_token"
    
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "8",
             "-H", f"Authorization: Bearer {token}",
             "-H", "Content-Type: application/json",
             "-d", '{"get_updates_buf":""}',
             ILINK_URL],
            capture_output=True, timeout=10
        )
        resp = r.stdout.decode(errors="replace").strip()
        if '"errcode":-14' in resp or '"ret":-14' in resp:
            return "expired", resp[:60]
        elif '"ret":0' in resp:
            return "ok", resp[:60]
        else:
            return "unknown", resp[:60]
    except Exception as e:
        return "error", str(e)

def check_profile(name):
    """完整检查一个profile的微信状态"""
    state_file = f"D:/hermes/hermes-data/profiles/{name}/gateway_state.json"
    if not os.path.exists(state_file):
        return None
    
    with open(state_file) as f:
        d = json.load(f)
    
    pid = d.get("pid", 0)
    alive = check_pid(pid)
    wx_state = d.get("platforms", {}).get("weixin", {}).get("state", "?")
    updated = d.get("updated_at", "")
    
    # iLink direct test
    ilink_status, ilink_msg = test_ilink(name)
    
    # Determine REAL status
    if not alive:
        real = "dead"
    elif ilink_status == "expired":
        real = "expired"
    elif ilink_status == "ok":
        real = "connected"
    elif wx_state == "connected" and ilink_status != "ok":
        real = "stale_connected"  # 假活
    else:
        real = wx_state
    
    return {
        "profile": name,
        "pid": pid,
        "alive": alive,
        "state_display": wx_state,
        "ilink_status": ilink_status,
        "ilink_msg": ilink_msg,
        "real_status": real,
    }

def run():
    profiles = ["mybot", "qqbot2", "qqbot3", "qqbot4"]
    log("=" * 55)
    log("看门狗v2 微信健康检查")
    log("=" * 55)
    
    alerts = []
    for p in profiles:
        result = check_profile(p)
        if not result:
            continue
        
        status_icon = {
            "connected": "✅",
            "dead": "💀",
            "expired": "⚠️",
            "stale_connected": "🔴",
            "retrying": "🔄",
            "disconnected": "❌",
        }.get(result["real_status"], "❓")
        
        log(f"  {p:8s} PID={result['pid']:<6} alive={result['alive']}  "
            f"state={result['state_display']}  iLink={result['ilink_status']}  "
            f"{status_icon} real={result['real_status']}")
        
        if result["real_status"] in ["expired", "dead", "stale_connected"]:
            alerts.append(f"{p}: {result['real_status']}")
    
    if alerts:
        log(f"⚠ ALERTS: {', '.join(alerts)}")
        # Send to working platforms
        for p in profiles:
            if os.path.exists(f"D:/hermes/hermes-data/profiles/{p}/.env"):
                for plat in ["qqbot"]:
                    try:
                        msg = f"⚠ 微信连接异常: {', '.join(alerts)}"
                        subprocess.run(
                            ["hermes", "--profile", p, "send", "-t", plat, msg],
                            capture_output=True, timeout=10
                        )
                    except:
                        pass
                break
    else:
        log("✅ 全部正常")

if __name__ == "__main__":
    run()
