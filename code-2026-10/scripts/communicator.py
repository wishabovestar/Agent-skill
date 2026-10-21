#!/usr/bin/env python3
"""
通联 — 平台连接监控与自主修复Agent v2.0
==========================================
定期检查各平台连接状态，检测gateway崩溃并修复。

v2.0 改进:
  - 增加stale state检测（state.json显示running但进程已死）
  - PID真实存活验证（tasklist代替kill -0）
  - DETACHED_PROCESS方式重启（唯一可靠方式，绕过TUI子进程管理）
  - 修复脚本自身异常退出时输出明确错误码
  - 增加升级告警通道（严重时deliver=all通知用户）

用法:
  python communicator.py              # 仅检查，不修复
  python communicator.py --fix        # 检查+自主修复
  python communicator.py --force-repair  # 强制修复（即使state正常）
"""
import json, os, subprocess, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── 路径配置 ──────────────────────────────────
HOME = "D:\\hermes\\hermes-data\\profiles\\mybot"
STATE_FILE = os.path.join(HOME, "gateway_state.json")
LOG_DIR = os.path.join(HOME, "logs")
EXIT_LOG = os.path.join(LOG_DIR, "gateway-exit-diag.log")
CRASH_LOG = os.path.join(LOG_DIR, "tui_gateway_crash.log")

HERMES_CLI = os.path.join(os.path.dirname(sys.executable), "hermes")
if not os.path.exists(HERMES_CLI + ".exe"):
    HERMES_CLI = "hermes"  # fallback to PATH
STALE_THRESHOLD_MIN = 10   # state.json超过N分钟未更新→僵尸
FIX_WAIT = 20              # 修复后等待秒数
GBK_CRASH_INTERVAL = 15    # GBK崩溃间隔(分钟)，用于识别高频崩溃

# ── 出口码 ──
EXIT_HEALTHY = 0
EXIT_WARNING = 1
EXIT_CRITICAL = 2
EXIT_ERROR = 3


def log(msg: str, level: str = "INFO", stderr: bool = False):
    """统一日志输出"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, file=sys.stderr if stderr else sys.stdout)
    # 写文件
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, "communicator.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def check_pid(pid: int) -> bool:
    """Windows上确认PID真实存活（tasklist输出为GBK编码）"""
    if not pid or pid <= 0:
        return False
    try:
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True, timeout=10
        )
        stdout = r.stdout.decode("gbk", errors="replace")
        return str(pid) in stdout
    except:
        return False


def read_state() -> dict:
    """读取gateway_state.json"""
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log(f"状态文件解析失败: {e}", "ERROR", stderr=True)
        return {}


def check_gbk_crash_history(window_minutes: int = 60) -> dict:
    """检查最近N分钟内tui_gateway_crash.log中是否有GBK崩溃"""
    if not os.path.exists(CRASH_LOG):
        return {"has_gbk_crash": False, "count": 0, "latest": None}
    
    try:
        with open(CRASH_LOG, "r", encoding="utf-8") as f:
            content = f.read()
        
        import re
        crashes = re.findall(
            r"UnicodeDecodeError: 'gbk' codec can't decode byte 0x[0-9a-f]+",
            content
        )
        # 找最新时间
        times = re.findall(r"thread exception.*?(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", content)
        latest = times[-1] if times else None
        
        # 只计算窗口内崩溃
        if latest and window_minutes < 1440:
            try:
                latest_dt = datetime.strptime(latest, "%Y-%m-%d %H:%M:%S")
                cutoff = datetime.now() - timedelta(minutes=window_minutes)
                # 粗略计数：只保留窗口内的
                recent_count = 0
                for t in reversed(times):
                    t_dt = datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
                    if t_dt >= cutoff:
                        recent_count += 1
                    else:
                        break
                return {"has_gbk_crash": recent_count > 0, "count": recent_count, "latest": latest}
            except:
                pass
        
        return {
            "has_gbk_crash": len(crashes) > 0,
            "count": len(crashes),
            "latest": latest,
        }
    except:
        return {"has_gbk_crash": False, "count": 0, "latest": None}


def should_restart_detached() -> bool:
    """判断是否应该用DETACHED_PROCESS方式（绕过TUI）"""
    # 如果近1小时内GBK崩溃≥3次，说明PYTHONUTF8未完全生效，必须用detached
    gbk = check_gbk_crash_history(window_minutes=60)
    return gbk["count"] >= 3


def read_exit_log_latest() -> dict:
    """读取gateway-exit-diag.log，判断最后一个gateway是否异常退出"""
    if not os.path.exists(EXIT_LOG):
        return {"has_clean_exit": False, "last_pid": 0}
    
    try:
        clean_exit_found = False
        last_pid = 0
        with open(EXIT_LOG, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    tag = d.get("tag", "")
                    pid = d.get("pid", 0)
                    if tag == "gateway.exit_clean":
                        clean_exit_found = True
                        last_pid = pid
                except:
                    pass
        return {"has_clean_exit": clean_exit_found, "last_pid": last_pid}
    except:
        return {"has_clean_exit": False, "last_pid": 0}


def diagnose(state: dict) -> dict:
    """完整诊断"""
    pid = state.get("pid", 0)
    gw_state = state.get("gateway_state", "unknown")
    updated = state.get("updated_at", "")
    platforms = state.get("platforms", {})
    
    result = {
        "pid": pid,
        "pid_alive": check_pid(pid),
        "gateway_state": gw_state,
        "state_age_min": 0,
        "state_stale": False,
        "platforms": {},
        "issues": [],
        "has_gbk_crash": False,
        "gbk_crash_count": 0,
        "severity": "healthy",  # healthy / warning / critical
    }
    
    # 状态文件新鲜度
    if updated:
        try:
            updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            age_min = (now - updated_dt).total_seconds() / 60
            result["state_age_min"] = round(age_min, 1)
            if age_min > STALE_THRESHOLD_MIN:
                result["state_stale"] = True
                result["issues"].append(f"状态文件{age_min:.0f}分钟未更新(>{STALE_THRESHOLD_MIN})")
        except:
            pass
    
    # 存活检测
    if pid and not result["pid_alive"]:
        result["issues"].append(f"PID {pid} 已死亡(stale state陷阱)")
        result["severity"] = "critical"
        # 查崩溃根因
        exit_log = read_exit_log_latest()
        if not exit_log["has_clean_exit"]:
            result["issues"].append("异常崩溃(exit日志缺clean标签)")
        
        gbk = check_gbk_crash_history()
        if gbk["has_gbk_crash"]:
            result["has_gbk_crash"] = True
            result["gbk_crash_count"] = gbk["count"]
            result["issues"].append(f"GBK编码崩溃(gbk crash #{gbk['count']}次)")
    
    # 平台状态
    for name, info in platforms.items():
        ps = info.get("state", "unknown")
        err = info.get("error_message", "")
        if ps == "connected":
            result["platforms"][name] = "✅"
        elif ps == "retrying":
            result["platforms"][name] = "🔄"
            if result["severity"] != "critical":
                result["severity"] = "warning"
        else:
            result["platforms"][name] = "❌"
            if result["severity"] != "critical":
                result["severity"] = "warning"
    
    if result["severity"] == "healthy" and not result["pid_alive"] and pid:
        result["severity"] = "critical"
    
    return result


def restart_gateway_detached() -> bool:
    """DETACHED_PROCESS方式重启gateway（绕过TUI，唯一可靠方式）"""
    launcher = os.path.join(HOME, "gateway-service", "launcher.py")
    # 如果launcher.py不存在，直接生成临时启动脚本
    if not os.path.exists(launcher):
        log("⚠ launcher.py 不存在，生成临时启动脚本", "WARN")
        # 获取hermes可执行路径（优先用当前Python所在的Scripts目录）
        hermes_dir = os.path.dirname(sys.executable)  # e.g. .../venv/Scripts/
        hermes_exe = os.path.join(hermes_dir, "hermes.exe")
        if not os.path.exists(hermes_exe):
            # 回退1: 用python -m hermes方式
            hermes_exe = f'"{sys.executable}" -m hermes_cli'
        launcher_py = f"""
import subprocess, os
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
subprocess.Popen(
    [{hermes_exe}, "gateway", "run", "--replace"],
    env=os.environ,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
)
"""
        launcher_py_path = os.path.join(HOME, "gateway-service", "launcher_detached.py")
        with open(launcher_py_path, "w") as f:
            f.write(launcher_py)
        launcher = launcher_py_path
    
    try:
        log("Step 1: 停止旧 gateway...", "WARN")
        subprocess.run(
            [HERMES_CLI, "--profile", "mybot", "gateway", "stop"],
            capture_output=True, text=True, timeout=15
        )
        time.sleep(3)
        
        log(f"Step 2: DETACHED_PROCESS启动 ({launcher})...", "WARN")
        # 使用pythonw.exe在完全独立的进程中启动
        subprocess.Popen(
            ["pythonw.exe", launcher],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        
        log(f"Step 3: 等待 {FIX_WAIT} 秒让 gateway 启动...", "INFO")
        time.sleep(FIX_WAIT)
        
        # 验证
        state = read_state()
        new_pid = state.get("pid", 0)
        alive = check_pid(new_pid)
        
        if alive:
            platforms = state.get("platforms", {})
            connected = sum(1 for p in platforms.values() if p.get("state") == "connected")
            total = len(platforms)
            log(f"✅ 修复成功! PID={new_pid} 存活, 平台 {connected}/{total} 在线", "INFO")
            return True
        else:
            log(f"⚠ state显示running但PID {new_pid} 未存活", "WARN")
            return False
            
    except Exception as e:
        log(f"❌ 修复失败: {e}", "ERROR", stderr=True)
        return False


def run_check(fix: bool = False, force_repair: bool = False):
    """执行一次完整检查"""
    log("=" * 60)
    log("🔍 通联 v2.0 — 平台健康检查")
    log("=" * 60)
    
    state = read_state()
    if not state:
        log("❌ 无法读取 gateway_state.json，尝试直接恢复...", "WARN")
        # fallback: 用tasklist直接找gateway进程
        try:
            r = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"],
                capture_output=True, timeout=10
            )
            output = r.stdout.decode("gbk", errors="replace")
            import re
            pids = re.findall(r'"(\d+)"', output)
            log(f"  tasklist发现 {len(pids)} 个python进程")
            
            if fix:
                log("  → 状态文件不可读，直接强制重启gateway", "WARN")
                success = restart_gateway_detached()
                if success:
                    log("✅ 强制修复成功!", "INFO")
                    log("=" * 60)
                    sys.exit(EXIT_HEALTHY)
        except:
            pass
        
        log("❌ 无法恢复，gateway 可能未安装或Python环境异常", "ERROR", stderr=True)
        log("=" * 60)
        sys.exit(EXIT_CRITICAL)
    
    # 诊断
    d = diagnose(state)
    
    log(f"\nPID: {d['pid']} | 存活: {'✅' if d['pid_alive'] else '❌ 死亡'} | "
        f"State年龄: {d['state_age_min']}分钟 | 僵死: {'⚠️' if d['state_stale'] else '✅'}")
    log(f"Gateway状态: {d['gateway_state']} | 综合: {d['severity'].upper()}")
    
    for name, icon in d["platforms"].items():
        log(f"  {icon} {name}")
    
    if d["has_gbk_crash"]:
        log(f"\n⚠ GBK编码崩溃历史: {d['gbk_crash_count']}次")
        log("  → 建议: 重启电脑使 PYTHONUTF8=1 完全生效，或用DETACHED_PROCESS")
    
    # 判定是否要修复
    needs_fix = (force_repair or 
                 d["severity"] == "critical" or
                 not d["pid_alive"] or
                 d["state_stale"])
    
    if not needs_fix and not d["issues"]:
        log("\n✅ 一切正常")
        log("=" * 60)
        sys.exit(EXIT_HEALTHY)
    
    # 有异常→输出诊断
    if d["issues"]:
        log(f"\n⚠ 发现 {len(d['issues'])} 个问题:")
        for iss in d["issues"]:
            log(f"  • {iss}", "WARN")
    
    # 修复
    if fix and needs_fix:
        log("\n🔧 执行自主修复...", "WARN")
        
        # GBK高频崩溃→强制用DETACHED_PROCESS
        use_detached = d["has_gbk_crash"] or should_restart_detached()
        if use_detached:
            log("  → GBK高频崩溃检测到，使用 DETACHED_PROCESS 绕过TUI", "WARN")
        
        success = restart_gateway_detached()
        
        if success:
            log("\n✅ 修复完成! 所有平台应陆续恢复连接", "INFO")
        else:
            log("\n❌ 修复失败，需要手动重启", "ERROR", stderr=True)
            log("  手动命令: hermes --profile mybot gateway run --replace", "ERROR")
            # 严重失败→exit critical
            log("=" * 60)
            sys.exit(EXIT_CRITICAL)
    
    elif fix and not needs_fix:
        log("\n✅ 无需修复")
    
    log("=" * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="通联 — 平台连接监控 v2.0")
    parser.add_argument("--fix", action="store_true", help="启用自主修复")
    parser.add_argument("--force-repair", action="store_true", help="强制修复")
    
    args = parser.parse_args()
    run_check(fix=args.fix, force_repair=args.force_repair)


if __name__ == "__main__":
    main()
