#!/usr/bin/env python3
"""
Hermes 每日汇总报告脚本（22:00执行）
生成各平台Token消耗、任务完成、SubAgent交付的汇总报告。
输出格式为markdown，供cron投递。
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

# ⚠️ 原写法指向 ~/AppData/Local/hermes/profiles/mybot —— 该目录存在但【冻结在 2026-07-29】
#    ⇒ 日报连续 2.5 个月在报僵尸数据（"Cron 4 活跃"，实际 27）。改为 env 优先 + 真实回退。
HERMES_HOME = (os.environ.get("HERMES_HOME")
               or os.environ.get("HERMES_PROFILE_HOME")
               or r"D:/hermes/hermes-data/profiles/mybot")
CACHE_DIR = os.path.join(HERMES_HOME, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

def run_cmd(cmd_list):
    """运行命令并返回输出"""
    try:
        r = subprocess.run(cmd_list, capture_output=True, text=True, timeout=30)
        return r.stdout, r.stderr, r.returncode
    except Exception as e:
        return "", str(e), -1

def get_insights():
    """获取 hermes insights 数据。

    ⚠️ 原写法先试 `--json` —— 但本机 hermes **不支持 --json**（rc=2、stdout 为空），
       于是每次都要多跑一次；且失败时静默返回 ""（报告里 Token 段直接空掉，看不出是坏了）。
       ⇒ 现在只跑受支持的文本模式，并把失败原因带回报告。
    """
    exe = shutil.which("hermes") or "hermes"
    stdout, stderr, rc = run_cmd([exe, "insights", "--days", "1"])
    if rc != 0 or not stdout:
        return f"  ⚠️ insights 调用失败 (rc={rc}) {stderr.strip()[:120]}"
    return stdout

_GW_ERR = []


def get_gateway_state():
    """获取网关状态。

    ⚠️ 真实的 gateway_state.json **带 UTF-8 BOM** —— 用默认编码 json.load 会抛
       "Unexpected UTF-8 BOM"，被 except 吞掉后返回 None，
       于是【异常汇总】看不到任何平台 ⇒ 报告"✅ 无异常"。
       ⇒ 这是最危险的一类缺陷：**读不到 ⇒ 报正常**（宪法 P2：不得把"未找到"当"没有"）。
       现在：用 utf-8-sig，并把失败原因记下来供报告显式报出。
    """
    _GW_ERR.clear()
    path = os.path.join(HERMES_HOME, "gateway_state.json")
    if not os.path.exists(path):
        _GW_ERR.append(f"gateway_state.json 不存在: {path}")
        return None
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        _GW_ERR.append(f"读取失败 {type(e).__name__}: {e}")
        return None

def get_cron_jobs():
    """获取cron任务列表"""
    try:
        jobs_file = os.path.join(HERMES_HOME, "cron", "jobs.json")
        if os.path.exists(jobs_file):
            with open(jobs_file) as f:
                return json.load(f)
    except:
        pass
    return None

def get_session_count():
    """获取今日会话数"""
    try:
        state_file = os.path.join(HERMES_HOME, "state.db")
        if os.path.exists(state_file):
            # ⚠️ 本机 python3 不存在（只有 python / python.exe）⇒ 原写法静默返回 ""
            stdout, _, _ = run_cmd([sys.executable, "-c", f"""
import sqlite3
conn = sqlite3.connect(r'{state_file}')
# 今日会话数
c = conn.execute("SELECT COUNT(*) FROM sessions WHERE date(created_at) = date('now')").fetchone()[0]
print(f'SESSIONS={{c}}')
# 今日消息数
m = conn.execute("SELECT COUNT(*) FROM messages WHERE date(created_at) = date('now')").fetchone()[0]
print(f'MESSAGES={{m}}')
conn.close()
"""])
            return stdout.strip()
    except:
        pass
    return ""

def format_platform_icon(state):
    return "✅" if state == "connected" else "❌"

def main():
    now = datetime.now(timezone.utc)
    beijing = now.strftime("%Y-%m-%d %H:%M")

    report_parts = [
        f"📊 **Hermes 每日汇总报告**",
        f"🕐 {beijing} (UTC+8)",
        "─" * 35,
        ""
    ]

    # === 1. Token使用情况 ===
    insights = get_insights()
    report_parts.append("### 🤖 Token 消耗")
    if insights:
        # 尝试提取关键字段
        for line in insights.split("\n"):
            line_s = line.strip()
            if any(k in line_s for k in ["Total tokens", "Input tokens", "Output tokens", 
                                          "Sessions:", "Tool calls:", "Messages:"]):
                report_parts.append(f"  {line_s}")
            elif "deepseek" in line_s.lower() and "Tokens" in line_s:
                report_parts.append(f"  {line_s}")
            elif "Platform" in line_s or "平台" in line_s:
                continue
    report_parts.append("")

    # === 2. 平台连接状态 ===
    report_parts.append("### 🔌 平台连接状态")
    state = get_gateway_state()
    if state:
        # ⭐ 陈旧度：快照自身可能过时（本机实测该文件停在 5 天前）
        #    ⇒ 必须把"这份状态是什么时候的"一并报出，否则拿旧快照当现状。
        _upd = state.get("updated_at") or state.get("start_time") or "?"
        try:
            _ts = datetime.fromisoformat(str(_upd).replace("Z", "+00:00"))
            _age = (datetime.now(_ts.tzinfo or timezone.utc) - _ts).total_seconds() / 3600
            _age_s = f"{_age:.1f}h 前"
            _stale = _age > 6
        except Exception:
            _age_s, _stale = str(_upd)[:19], False
        report_parts.append(f"  🕐 状态快照: {_age_s}" + ("  ⚠️ **陈旧**（>6h，可能非当前）" if _stale else ""))
        gw = state.get("gateway_state", "unknown")
        report_parts.append(f"  VPN/Proxy: {'✅ 运行中' if gw=='running' else '❌ ' + gw}")
        for name, info in state.get("platforms", {}).items():
            pstate = info.get("state", "?")
            icon = format_platform_icon(pstate)
            report_parts.append(f"  {icon} **{name}**: {pstate}")
    else:
        report_parts.append("  ⚠️ 无法读取网关状态")
    report_parts.append("")

    # === 3. 任务/SubAgent情况 ===
    report_parts.append("### 📋 SubAgent 与 Cron 任务")
    
    # Cron任务
    jobs = get_cron_jobs()
    if jobs:
        job_list = jobs if isinstance(jobs, list) else jobs.get("jobs", [])
        active = sum(1 for j in job_list if j.get("enabled", False))
        report_parts.append(f"  ⏰ Cron任务: {active} 活跃")
        for j in job_list:
            if j.get("enabled", False):
                name = j.get("name", "?")
                last = j.get("last_status", "无") or "无"
                report_parts.append(f"    • {name}: 上次状态={last}")
    else:
        report_parts.append("  ⏰ Cron任务: 无数据")
    
    # 活跃Agent
    if state:
        active_agents = state.get("active_agents", 0)
        report_parts.append(f"  🧠 当前活跃Agent: {active_agents}")
    report_parts.append("")

    # === 4. 网络连通性检查 ===
    report_parts.append("### 🌐 网络连通性")
    import socket, time
    targets = [
        ("DeepSeek", "api.deepseek.com"),
        ("DingTalk", "oapi.dingtalk.com"),
        ("GitHub", "api.github.com"),
    ]
    for name, host in targets:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            start = time.time()
            r = s.connect_ex((host, 443))
            t = time.time() - start
            s.close()
            icon = "✅" if r == 0 else "❌"
            # ⚠️ 原写法 f"{t:.0f}ms" —— t 是【秒】，故 <0.5s 全打成 "0ms"（实测三站全 0ms）
            report_parts.append(f"  {icon} {name}: {t*1000:.0f}ms")
        except:
            report_parts.append(f"  ❌ {name}: 超时")
    report_parts.append("")

    # === 5. 异常汇总 ===
    report_parts.append("### ⚠️ 异常汇总")
    issues = []
    
    # 平台异常
    if state:
        for name, info in state.get("platforms", {}).items():
            if info.get("state") != "connected":
                issues.append(f"  🚨 {name} 断开连接")
            err_msg = info.get("error_message")
            if err_msg:
                issues.append(f"  ⚠️ {name} 错误: {err_msg}")
    
    if state and state.get("gateway_state") != "running":
        issues.append(f"  🚨 网关状态异常: {state.get('gateway_state')}")
    
    # ⚠️ 关键闸：state 读不到 ⇒ 能力不足，必须【显式报"无法判定"】，
    #    不得因为 issues 为空就打印"✅ 无异常"（那是把"未检查"说成"检查过且没问题"）。
    if state is None:
        report_parts.append("  ⚠️ **无法判定**：网关状态未取到 ⇒ 平台异常【未检查】")
        for e in _GW_ERR:
            report_parts.append(f"      原因: {e}")
    elif not issues:
        report_parts.append("  ✅ 无异常（已检查 %d 个平台）"
                            % len(state.get("platforms", {})))
    else:
        report_parts.extend(issues)
    
    report_parts.append("")
    report_parts.append("─" * 35)
    report_parts.append(f"🔄 报告生成完成")

    print("\n".join(report_parts))

if __name__ == "__main__":
    main()
