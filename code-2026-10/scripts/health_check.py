#!/usr/bin/env python3
"""
Hermes 多平台故障监控脚本
检查各平台网络连通性、网关状态、响应超时
异常时输出告警信息（通过cron no_agent模式静默/告警）
"""
import json
import os
import socket
import time
import subprocess
from datetime import datetime, timezone

HERMES_HOME = os.path.expanduser("~/AppData/Local/hermes/profiles/mybot")

def ts_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def check_gateway():
    """检查网关进程是否存活"""
    state_file = os.path.join(HERMES_HOME, "gateway_state.json")
    try:
        if not os.path.exists(state_file):
            return "❌ gateway_state.json 不存在"
        with open(state_file) as f:
            state = json.load(f)
        pid = state.get("pid")
        gw_state = state.get("gateway_state")
        if not pid:
            return "❌ 无网关PID"
        # 检查进程是否存在（Windows: tasklist, POSIX: kill -0）
        import subprocess
        try:
            if os.name == "nt":
                r = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True, timeout=10
                )
                alive = str(pid) in (r.stdout.decode("gbk", errors="replace"))
            else:
                os.kill(pid, 0)
                alive = True
        except OSError:
            alive = False
        if not alive:
            return f"❌ 网关进程 {pid} 已不存在"
        if gw_state != "running":
            return f"⚠️ 网关状态异常: {gw_state}"
        platforms = state.get("platforms", {})
        return ("ok", platforms, pid)
    except Exception as e:
        return f"❌ 读取网关状态失败: {e}"

def check_platform_connectivity(platforms):
    """检查各平台连接状态"""
    alerts = []
    for name, info in platforms.items():
        p_state = info.get("state", "unknown")
        p_time = info.get("updated_at", "")
        if p_state != "connected":
            alerts.append(f"🚨 {name}: 状态={p_state} (最后更新: {p_time})")
    return alerts

def check_network(targets):
    """检查外网连通性"""
    alerts = []
    results = {}
    for name, host, port, timeout in targets:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            start = time.time()
            result = s.connect_ex((host, port))
            elapsed = time.time() - start
            s.close()
            ok = result == 0
            results[name] = ("ok" if ok else "fail", elapsed)
            if not ok:
                alerts.append(f"🚨 {name}: 网络不可达 ({host}:{port}, {elapsed:.1f}s)")
        except Exception as e:
            results[name] = ("error", str(e))
            alerts.append(f"🚨 {name}: 检测异常 - {e}")
    return alerts, results

def check_last_response():
    """检查各平台最后响应时间，判断是否长时间无响应"""
    # 读取session或日志来判断最后活跃时间
    # 简单方案：检查gateway_state中各平台的更新时间
    alerts = []
    state_file = os.path.join(HERMES_HOME, "gateway_state.json")
    try:
        with open(state_file) as f:
            state = json.load(f)
        platforms = state.get("platforms", {})
        now = time.time()
        for name, info in platforms.items():
            updated = info.get("updated_at", "")
            if updated:
                try:
                    # 尝试解析ISO时间
                    t = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    age_hours = (datetime.now(timezone.utc) - t).total_seconds() / 3600
                    if age_hours > 1:  # 超过1小时无更新
                        alerts.append(f"⚠️ {name}: 最后活跃 {age_hours:.1f}小时前")
                except:
                    pass
    except:
        pass
    return alerts

def main():
    alerts = []
    info_lines = []

    # 1. 检查网关
    gw = check_gateway()
    if isinstance(gw, tuple) and gw[0] == "ok":
        _, platforms, pid = gw
        info_lines.append(f"✅ 网关运行中 (PID: {pid})")
        # 平台连接状态
        plat_alerts = check_platform_connectivity(platforms)
        alerts.extend(plat_alerts)
    else:
        alerts.append(f"🚨 网关异常: {gw}")

    # 2. 检查网络连通性
    net_targets = [
        ("DeepSeek API", "api.deepseek.com", 443, 5),
        ("DingTalk API", "oapi.dingtalk.com", 443, 5),
        ("GitHub API", "api.github.com", 443, 5),
    ]
    net_alerts, net_results = check_network(net_targets)
    alerts.extend(net_alerts)

    # 3. 检查各平台最后响应时间
    stale_alerts = check_last_response()
    alerts.extend(stale_alerts)

    # 4. 组装输出（仅在有问题时输出）
    if not alerts:
        # 静默：一切正常，不输出任何内容
        return

    # 构建告警消息
    msg_parts = [
        "🚨 **Hermes 平台告警**",
        f"🕐 {ts_now()}",
        "─" * 30
    ]
    for a in alerts:
        msg_parts.append(a)

    msg_parts.append("─" * 30)
    msg_parts.append("📡 网络状态:")
    for name, (status, extra) in net_results.items():
        icon = "✅" if status == "ok" else "❌"
        msg_parts.append(f"  {icon} {name}: {extra:.1f}s" if isinstance(extra, float) else f"  {icon} {name}: {extra}")

    # 输出告警（cron no_agent模式会捕获此输出并投递）
    print("\n".join(msg_parts))

if __name__ == "__main__":
    main()
