#!/usr/bin/env python3
"""
通联网关健康检查 (轻量脚本版 — 替代agent型 cron, 零LLM token)
====================================================
原agent型: 每30分消耗 ~15万 token (LLM上下文注入)
本脚本: 纯Python读取状态+验证PID, 零token消耗
输出: JSON状态 (有异常→输出详情; 正常→短状态)
"""
# side_effects: [写数据文件]
import os
import json, os, sys, glob
import subprocess
from datetime import datetime

GATEWAY_FILES = []
for prof in ["qqbot3", "mybot", "qqbot2"]:
    p = f"D:/hermes/hermes-data/profiles/{prof}/gateway_state.json"
    if os.path.exists(p):
        GATEWAY_FILES.append(p)

def check_pid(pid):
    """Windows: 多级进程存活检测

    ★ R1080 加固 (2026-09-15):
      原实现首选 PowerShell Get-Process — 冷启动慢 (实测 cron 环境下 15s+ 超时),
      且【不检查进程是否真是该 profile 的网关】→ 误判/反复拉起。
      → 改为 psutil 快速检测 + profile 参数绑定 (确认是目标 profile 的网关)
    """
    if not pid:
        return False
    # 1) 首选: psutil (毫秒级, 无冷启动)
    try:
        import psutil
        return psutil.pid_exists(int(pid))
    except Exception:
        pass
    # 2) fallback: PowerShell
    try:
        import subprocess
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-Process -Id {pid} -ErrorAction SilentlyContinue"],
            capture_output=True, timeout=10)
        if r.returncode == 0 and f"{pid}".encode() in r.stdout:
            return True
    except Exception:
        pass
    # 3) fallback: tasklist (兼容旧环境)
    try:
        import subprocess
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True,
                           text=True, encoding="gbk", errors="replace", timeout=10)
        if str(pid) in r.stdout:
            return True
    except Exception:
        pass
    return False


def gateway_proc_alive(prof):
    """★ R1080: 按 profile 检测网关进程是否存活 (比读 state.pid 可靠)

    state.json 可能是【遗留文件】(pid 字段为空/过期) → 只看 state 会误判。
    这里直接扫进程命令行, 确认有 `--profile <prof> ... gateway` 进程。
    """
    try:
        import psutil
        for p in psutil.process_iter(["pid", "cmdline"]):
            try:
                c = " ".join(p.info.get("cmdline") or [])
                if f"--profile {prof}" in c and "gateway" in c:
                    return p.info["pid"]
            except Exception:
                continue
    except Exception:
        pass
    return None


def _unused_legacy_pid_check():
    """保留占位 (原 update_time 兜底逻辑, 已被 gateway_proc_alive 取代)"""
    if False:
        for f in []:
            d = json.load(open(f))
            if (d.get("pid") == 0 or d.get("process_pid") == 0
                    or d.get("gateway_pid") == 0):
                ut = d.get("update_time") or d.get("updated_at") or d.get("last_heartbeat")
                if ut:
                    ts = None
                    try:
                        ts = float(ut) if isinstance(ut, (int, float)) else None
                    except (ValueError, TypeError):
                        pass
                    if ts is not None:
                        from datetime import datetime
                        age = (datetime.now() - datetime.fromtimestamp(ts)).total_seconds()
                        return age < 1800  # 30分钟内更新过
    return None  # 完全无法确定


def main():
    report = {"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "profiles": {}}
    issues = []
    for f in GATEWAY_FILES:
        prof = os.path.basename(os.path.dirname(f))
        try:
            d = json.load(open(f))
            pid = d.get("pid") or d.get("process_pid") or d.get("gateway_pid") or 0
            connected = d.get("connected", d.get("platform", d.get("status", "unknown")))
            pid_alive = check_pid(pid) if pid else False
            # ★ R1080: state.pid 可能是遗留/过期 → 用真实进程扫描兜底
            #   (qqbot2 曾因 state pid 为空被反复误拉起)
            real_pid = gateway_proc_alive(prof)
            if real_pid:
                pid_alive = True
                pid = real_pid
                connected = "connected"
            status = "OK" if (pid_alive and connected not in ("disconnected", "error", False)) else "ISSUE"
            report["profiles"][prof] = {"pid": pid, "pid_alive": pid_alive,
                                        "connected": connected, "status": status}
            if status != "OK":
                issues.append(f"{prof}: PID{alive_str(pid_alive)} 连接{connected}")
        except Exception as e:
            report["profiles"][prof] = {"status": "ERROR", "err": str(e)}
            issues.append(f"{prof}: {e}")

    report["total_ok"] = all(p["status"] == "OK" for p in report["profiles"].values()) if report["profiles"] else False
    # --- ★★★ 防复发加固 2026-09-15: 自动拉起缺失的网关 (R1080) ---
    # 根因: 计划任务 HermesGatewayStartup 用裸命令 `pythonw` (不在任务计划的 PATH)
    #   → 0x80070002 文件未找到 → 开机自启【静默失败】
    #   → 09:19 重启后 qqbot3 网关未拉起 → 微信断联
    # 修复: 健康检查发现 ISSUE 时【主动拉起】(不依赖计划任务/管理员权限)
    AUTOSTART = os.environ.get("GATEWAY_AUTOSTART", "1") == "1"
    if issues and AUTOSTART:
        launched = []
        for prof in ("qqbot3", "qqbot2", "mybot"):
            st = report["profiles"].get(prof, {})
            if st.get("status") == "OK":
                continue
            # 检查是否已有存活进程 (避免重复拉起)
            if st.get("pid_alive"):
                continue
            hermes_exe = None
            for cand in (
                rf"D:\hermes\hermes-data\profiles\{prof}\hermes-agent\venv\Scripts\hermes.exe",
                r"C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe",
                r"D:\hermes\hermes-data\profiles\mybot\hermes-agent\venv\Scripts\hermes.exe",
            ):
                if os.path.exists(cand):
                    hermes_exe = cand
                    break
            if not hermes_exe:
                launched.append(f"{prof}: 找不到 hermes.exe")
                continue
            try:
                env = os.environ.copy()
                if prof == "mybot":      # mybot 微信已禁用 — 清 env 防抢 token
                    for k in ("WEIXIN_TOKEN", "WEIXIN_APP_ID", "WEIXIN_APP_SECRET"):
                        env.pop(k, None)
                kw = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          stdin=subprocess.DEVNULL, env=env)
                # Windows: 新进程组 + 分离
                if os.name == "nt":
                    kw["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP
                                           | 0x00000008)   # DETACHED_PROCESS
                else:
                    kw["start_new_session"] = True
                subprocess.Popen([hermes_exe, "--profile", prof, "gateway", "run"],
                                 **kw)
                launched.append(f"{prof}: 已拉起")
            except Exception as e:
                launched.append(f"{prof}: 拉起失败 {str(e)[:50]}")
        if launched:
            report["autostart"] = launched
            issues.append(f"自动拉起: {'; '.join(launched)}")
    # --- 防复发加固 2026-09-04: 微信 DNS 通道预检 (06:15-08:02 DNS 事件教训) ---
    # ilinkai.weixin.qq.com 解析失败会致早报/巡天投递全败 (采集成功但用户收不到)
    import socket
    try:
        socket.getaddrinfo("ilinkai.weixin.qq.com", 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
        report["weixin_dns"] = "OK"
    except Exception as e:
        report["weixin_dns"] = f"FAIL: {e}"
        issues.append(f"weixin DNS FAIL: {e} (投递通道可能断 — 早报/巡天会投递失败)")
    # 输出: 有issues输出详情, 无issues输出极简状态(节省)
    if issues:
        report["issues"] = issues
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[GATEWAY-OK] {report['time']} profiles均在线: {list(report['profiles'].keys())}")

def alive_str(a):
    return "存活" if a else "未知" if a is None else "死亡"

if __name__ == "__main__":
    main()