#!/usr/bin/env python3
"""
gateway_monitor.py — 平台通联通联自检 + 微信状态历史记录

功能：
1. 检测 mybot gateway 各平台连接状态
2. 记录微信平台状态变化到历史日志 (weixin_status_history.csv)
3. 简约输出：异常时报警，正常时静默

配合 cron 使用: no_agent=true script=scripts/gateway_monitor.py schedule="every 5m"
"""
import json, os, sys, time
from datetime import datetime, timezone

HOME = os.path.expanduser("~/AppData/Local/hermes/profiles/mybot")
STATE_FILE = os.path.join(HOME, "gateway_state.json")
HISTORY_FILE = os.path.join(HOME, "logs", "weixin_status_history.csv")
MAX_AGE = 300  # 5分钟无更新视为僵尸

def ensure_log_dir():
    log_dir = os.path.join(HOME, "logs")
    os.makedirs(log_dir, exist_ok=True)

def load_history():
    """加载历史状态记录"""
    records = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("ts,"):
                    records.append(line)
    return records

def append_history(ts_local, ts_utc, status, latency_s, detail):
    """追加一条状态记录"""
    line = f"{ts_local},{ts_utc},{status},{latency_s},{detail}\n"
    # 先看是否需要写表头
    if not os.path.exists(HISTORY_FILE):
        header = "ts_local,ts_utc,status,latency_s,detail\n"
        with open(HISTORY_FILE, "w") as f:
            f.write(header)
    with open(HISTORY_FILE, "a") as f:
        f.write(line)

def check():
    ensure_log_dir()
    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ts_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    if not os.path.exists(STATE_FILE):
        append_history(now_local, ts_utc, "NO_FILE", -1, "gateway_state.json 不存在")
        print("[monitor] ❌ 无状态文件，gateway 未运行")
        return False

    with open(STATE_FILE) as f:
        state = json.load(f)

    pid = state.get("pid", 0)
    gw_state = state.get("gateway_state", "unknown")
    updated_raw = state.get("updated_at", "")
    
    # 计算延迟（状态文件距现在多久）
    latency = -1
    if updated_raw:
        try:
            updated_dt = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
            latency = int((now_utc - updated_dt).total_seconds())
        except:
            pass

    platforms = state.get("platforms", {})

    # ---- 微信平台专检 ----
    weixin = platforms.get("weixin", {})
    wx_state = weixin.get("state", "unknown")
    wx_detail = f"state={wx_state}"
    if weixin.get("error_code"):
        wx_detail += f" err={weixin['error_code']}:{weixin.get('error_message','')}"
    wx_updated = weixin.get("updated_at", "")
    if wx_updated:
        wx_detail += f" @{wx_updated}"

    # 写入历史
    append_history(now_local, ts_utc, wx_state, latency, wx_detail)

    # ---- 全平台检查 ----
    all_connected = all(
        p.get("state") == "connected" for p in platforms.values()
    )
    offline = [k for k, v in platforms.items() if v.get("state") != "connected"]

    # 状态文件老化检测
    if latency > MAX_AGE:
        print(f"[monitor] ⚠️ 状态文件已 {latency}s 未更新，gateway 可能僵死 (PID={pid})")
        return False

    if gw_state != "running":
        print(f"[monitor] ❌ gateway 状态={gw_state} (PID={pid})")
        return False

    if wx_state != "connected":
        print(f"[monitor] ⚠️ 微信离线: {wx_detail}")
        return False

    if not all_connected:
        print(f"[monitor] ⚠️ 平台离线: {offline}")
        return False

    # 一切正常 → 静默（cron 空输出不推送）
    # 但如有历史异常恢复，仍报一次
    records = load_history()
    if records:
        last_line = records[-1]
        last_status = last_line.split(",")[2] if len(last_line.split(",")) > 2 else ""
        if last_status != "connected":
            print(f"[monitor] ✅ 已恢复，全部在线 (PID={pid})")

    return True

if __name__ == "__main__":
    ok = check()
    # cron no_agent=true: 静默通过空输出实现「无异常不推送」
    sys.exit(0 if ok else 1)
