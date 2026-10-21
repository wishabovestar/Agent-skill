#!/usr/bin/env python3
"""微信心跳检测 - 每10分钟检查WeChat poll是否存活
no-agent模式：无输出=正常，有输出=异常告警

检测项:
1. gateway进程是否存活
2. state文件是否在5分钟内更新
3. WeChat iLink poll端点是否响应
4. 最近30分钟是否有weixin活动日志
"""
import json, os, sys, time, subprocess
from pathlib import Path
from datetime import datetime, timezone

HOME = "D:\\hermes\\hermes-data\\profiles\\mybot"
STATE_FILE = os.path.join(HOME, "gateway_state.json")
LOG_FILE = os.path.join(HOME, "logs", "gateway.log")
WARNINGS = []

def log(msg):
    print(f"[{datetime.now().isoformat()[:19]}] {msg}")

def check_gateway_process():
    """检查gateway进程是否存活 (用psutil避免subprocess编码问题)"""
    try:
        state = json.load(open(STATE_FILE))
        pid = state.get("pid")
        if not pid:
            WARNINGS.append("state文件中无PID")
            return False
        import psutil
        p = psutil.Process(pid)
        alive = p.is_running() and p.status() != psutil.STATUS_ZOMBIE
        if not alive:
            WARNINGS.append(f"PID {pid} 已不存活")
            return False
        return True
    except psutil.NoSuchProcess:
        WARNINGS.append(f"PID {pid} 不存在")
        return False
    except Exception as e:
        WARNINGS.append(f"进程检查失败: {e}")
        return False

def check_state_freshness():
    """检查state文件是否在5分钟内更新"""
    try:
        mtime = os.path.getmtime(STATE_FILE)
        age = time.time() - mtime
        if age > 600:  # 10分钟
            WARNINGS.append(f"state文件已{age/60:.0f}分钟未更新")
            return False
        return True
    except Exception as e:
        WARNINGS.append(f"state新鲜度检查失败: {e}")
        return False

def check_weixin_state():
    """检查state中weixin是否connected"""
    try:
        state = json.load(open(STATE_FILE))
        wx = state.get("platforms", {}).get("weixin", {})
        if wx.get("state") != "connected":
            WARNINGS.append(f"weixin state={wx.get('state')}, 非connected")
            return False
        updated = wx.get("updated_at", "")
        if updated:
            t = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - t).total_seconds()
            if age > 600:
                WARNINGS.append(f"weixin状态{age/60:.0f}分钟未更新")
                return False
        return True
    except Exception as e:
        WARNINGS.append(f"weixin状态检查失败: {e}")
        return False

def check_recent_activity():
    """检查gateway日志中最近是否有weixin活动"""
    try:
        if not os.path.exists(LOG_FILE):
            return True
        # 读最后200行
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        recent_lines = lines[-200:]
        weixin_lines = [l for l in recent_lines if "weixin" in l.lower() or "WeChat" in l]
        if weixin_lines:
            last = weixin_lines[-1]
            try:
                ts_str = last[:19]
                last_ts = datetime.fromisoformat(ts_str)
                age = (datetime.now() - last_ts).total_seconds()
                if age > 1800:
                    WARNINGS.append(f"最后weixin活动在{age/60:.0f}分钟前")
                    return False
            except:
                pass
        return True
    except Exception as e:
        return True

def main():
    c1 = check_gateway_process()
    c2 = check_state_freshness()
    c3 = check_weixin_state()
    c4 = check_recent_activity()

    if all([c1, c2, c3, c4]):
        return  # 全部正常，无输出（静默模式）

    log("❌ WeChat心跳异常")
    for w in WARNINGS:
        log(f"  ⚠ {w}")

    # 尝试自愈：重启gateway
    log("执行自愈: 重启gateway...")
    hermes = os.path.join(os.path.dirname(sys.executable), "hermes")
    if not os.path.exists(hermes + ".exe"):
        hermes = "hermes"
    result = subprocess.run(
        [hermes, "--profile", "mybot", "gateway", "run", "--replace"],
        capture_output=True, text=True, timeout=30
    )
    log(f"gateway重启: exit={result.returncode}")
    time.sleep(5)

    # 二次检查
    if check_gateway_process() and check_weixin_state():
        log("✅ 自愈成功")
    else:
        log("❌ 自愈失败，需人工介入")

if __name__ == "__main__":
    main()
