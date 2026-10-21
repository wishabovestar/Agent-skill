"""
看门狗v3 — 全平台复合健康检测 + 自动修复
Layer 1-7: 检测
Layer 8: 自动修复 (PID死亡 → 重启)
Layer 9: State实时化
Layer 10: 重启录仪

FIXES APPLIED (2026-07-20):
  1. iLink token: 修复脱敏问题, 使用真实token
  2. Auto-repair: 覆盖所有4个profile (不再仅限mybot)
  3. State清理: 启动前pop已禁用platform的stale条目
"""
import json, subprocess, os, time
from pathlib import Path
from datetime import datetime
from collections import defaultdict

LOG = Path("D:/hermes/hermes-data/watchdog_v3.log")
RESTART_LOG = Path("D:/hermes/hermes-data/watchdog_restarts.json")
PROFILES = {"mybot": {}, "qqbot2": {}, "qqbot3": {}, "qqbot4": {}}
RESTART_COUNTS = defaultdict(list)

# 熔断器配置 (W1: 双层保护)
SHORT_CIRCUIT_MINUTES = 5
SHORT_CIRCUIT_MAX = 3      # 5分钟内3次 → 停15分钟
LONG_CIRCUIT_MINUTES = 30
LONG_CIRCUIT_MAX = 6        # 30分钟内6次 → 停2小时+告警
CIRCUIT_BREAKER_FILE = Path("D:/hermes/hermes-data/.circuit_breaker.json")

def check_circuit_breaker(profile):
    """双层熔断器: 短时+长时"""
    now = time.time()
    if CIRCUIT_BREAKER_FILE.exists():
        try:
            data = json.loads(CIRCUIT_BREAKER_FILE.read_text())
            entry = data.get(profile, {})
            until = entry.get("until", 0)
            reason = entry.get("reason", "")
            if until > now:
                remaining = int((until - now) / 60)
                log(f"  🚫 {profile}: 熔断器激活(剩余{remaining}分钟) reason={reason}")
                return False
        except:
            pass
    return True

def set_circuit_breaker(profile, minutes, reason):
    """设置熔断"""
    now = time.time()
    data = {}
    if CIRCUIT_BREAKER_FILE.exists():
        try:
            data = json.loads(CIRCUIT_BREAKER_FILE.read_text())
        except:
            pass
    data[profile] = {"until": now + minutes * 60, "reason": reason, "set_at": now}
    CIRCUIT_BREAKER_FILE.write_text(json.dumps(data, indent=2))
    log(f"  🔒 {profile}: 熔断{minutes}分钟 reason={reason}")

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} {msg}")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{ts} {msg}\n")

def load_restart_log():
    if RESTART_LOG.exists():
        try:
            return json.loads(RESTART_LOG.read_text())
        except:
            pass
    return {"mybot": [], "qqbot2": [], "qqbot3": [], "qqbot4": []}

def save_restart_log(data):
    RESTART_LOG.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def clean_old_restarts(restarts, minutes=30):
    now = time.time()
    cutoff = now - minutes * 60
    return [t for t in restarts if t > cutoff]

def check_pid(pid):
    """PID liveness check.

    FIX (2026-07-31): `tasklist /FI "PID eq X"` hangs indefinitely on this host
    (system-wide process-enumeration hang; plain `tasklist` also hangs), so the
    old tasklist-based check always timed out -> healthy gateways were judged
    dead and auto-repair restarted them every ~2.5 min (restart loop). Use
    OpenProcess (direct open by PID, no enumeration, cannot hang) as the primary
    check; keep `ps` as a POSIX fallback.
    """
    if not pid or pid <= 0:
        return False
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        SYNCHRONIZE = 0x00100000
        kernel32 = ctypes.windll.kernel32
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
        if h:
            try:
                code = ctypes.c_ulong()
                # STILL_ACTIVE == 259 means the process is alive
                if kernel32.GetExitCodeProcess(h, ctypes.byref(code)) and code.value == 259:
                    return True
                return False
            finally:
                kernel32.CloseHandle(h)
        # h == 0 -> access denied (elevated target) or dead: try fallbacks below
    except Exception:
        pass
    # fallback 1 (Windows): Get-Process SUCCEEDS for elevated targets where
    # OpenProcess is denied to a non-elevated caller (the host gateway runs elevated).
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "if (Get-Process -Id %d -ErrorAction SilentlyContinue) {'UP'}" % int(pid)],
                           capture_output=True, text=True, timeout=12)
        if "UP" in (r.stdout or ""):
            return True
        if r.returncode == 0:
            return False
    except Exception:
        pass
    # fallback 2: ps (POSIX)
    try:
        r = subprocess.run(["ps", "-p", str(pid)], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False

def clean_stale_platforms(profile):
    """清理state中已禁用平台的stale条目"""
    state_path = f"D:/hermes/hermes-data/profiles/{profile}/gateway_state.json"
    if not os.path.exists(state_path):
        return
    try:
        with open(state_path, encoding="utf-8-sig") as f:
            d = json.load(f)
        # 检查config.yaml的platforms.*.enabled
        config_path = f"D:/hermes/hermes-data/profiles/{profile}/config.yaml"
        disabled_platforms = set()
        if os.path.exists(config_path):
            import re
            with open(config_path) as f:
                content = f.read()
            if re.search(r'weixin:\s*\n\s+enabled:\s*false', content):
                disabled_platforms.add("weixin")
            if re.search(r'photon:\s*\n\s+enabled:\s*false', content):
                disabled_platforms.add("photon")
        # 如果.env中所有WEIXIN_*都被注释, 也视为禁用
        env_path = f"D:/hermes/hermes-data/profiles/{profile}/.env"
        if os.path.exists(env_path):
            has_weixin = False
            has_active_weixin = False
            with open(env_path) as f:
                for line in f:
                    if line.startswith("WEIXIN_") and not line.startswith("#"):
                        has_active_weixin = True
                    if "WEIXIN_" in line:
                        has_weixin = True
            if has_weixin and not has_active_weixin:
                disabled_platforms.add("weixin")
        # Pop disabled platforms from state
        modified = False
        for plat in list(d.get("platforms", {}).keys()):
            if plat in disabled_platforms:
                log(f"     State: 移除已禁用平台 {plat}")
                d["platforms"].pop(plat)
                modified = True
        if modified:
            with open(state_path, "w") as f:
                json.dump(d, f, indent=2)
            log(f"     ✅ state清理完成")
        return disabled_platforms
    except Exception as e:
        log(f"     ⚠ state清理异常: {e}")
        return set()

def auto_repair(profile):
    """Layer 8: 自动修复 — PID死亡时重启Gateway (含熔断器)"""
    # 0.21.5 MULTIPLEX: per-profile gateways are REFUSED. If the host gateway is
    # up it serves this profile -> nothing to repair. Never stop/run per profile.
    if host_gateway_up():
        return True
    # 熔断器检查
    if not check_circuit_breaker(profile):
        return False
    
    restart_data = load_restart_log()
    recent_30 = clean_old_restarts(restart_data.get(profile, []), minutes=LONG_CIRCUIT_MINUTES)
    recent_5 = clean_old_restarts(restart_data.get(profile, []), minutes=SHORT_CIRCUIT_MINUTES)

    # 短时熔断: 5分钟3次
    if len(recent_5) >= SHORT_CIRCUIT_MAX:
        set_circuit_breaker(profile, 15, f"短时熔断: {SHORT_CIRCUIT_MINUTES}分钟{len(recent_5)}次")
        return False
    
    # 长时熔断: 30分钟6次
    if len(recent_30) >= LONG_CIRCUIT_MAX:
        set_circuit_breaker(profile, 120, f"长时熔断: {LONG_CIRCUIT_MINUTES}分钟{len(recent_30)}次")
        return False
    
    log(f"  🔧 {profile}: 自动重启中...")
    try:
        # Step 0: 清理stale state
        clean_stale_platforms(profile)

        # Step 1: stop
        r = subprocess.run(["hermes", "--profile", profile, "gateway", "stop"],
                          capture_output=True, text=True, timeout=15)
        log(f"     Stop: {r.stdout[:40]}")
        time.sleep(5)

        # Step 2: Check PID is truly dead
        state_path = f"D:/hermes/hermes-data/profiles/{profile}/gateway_state.json"
        old_pid = 0
        if os.path.exists(state_path):
            with open(state_path, encoding="utf-8-sig") as f:
                d = json.load(f)
            old_pid = d.get("pid", 0)

        if check_pid(old_pid):
            log(f"     ⚠ PID {old_pid} still alive, force kill...")
            subprocess.run(["taskkill", "/F", "/PID", str(old_pid)], capture_output=True, timeout=5)
            time.sleep(3)

        # Step 3: start without --replace
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        proc = subprocess.Popen(
            ["hermes", "--profile", profile, "gateway", "run"],
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        )
        log(f"     Start: PID={proc.pid}")

        # Step 3.5: VERIFY gateway started (NEW - wait up to 30s for state.json)
        time.sleep(15)  # give it time to initialize
        state_path = f"D:/hermes/hermes-data/profiles/{profile}/gateway_state.json"
        new_pid = 0
        if os.path.exists(state_path):
            try:
                with open(state_path, encoding="utf-8-sig") as f:
                    d = json.load(f)
                new_pid = d.get("pid", 0)
            except:
                pass
        
        if new_pid > 0 and check_pid(new_pid):
            log(f"     ✅ 验证: 新gateway运行中 PID={new_pid}")
        else:
            log(f"     ⚠ 验证: state.json PID未更新, 可能启动失败")
            # Try one more wait and check
            time.sleep(20)
            if os.path.exists(state_path):
                try:
                    with open(state_path, encoding="utf-8-sig") as f:
                        d = json.load(f)
                    new_pid = d.get("pid", 0)
                    if new_pid > 0 and check_pid(new_pid):
                        log(f"     ✅ 二次验证: gateway运行中 PID={new_pid}")
                    else:
                        log(f"     ❌ 二次验证失败: PID={new_pid} 不存活")
                except:
                    log(f"     ❌ 二次验证: state.json读取失败")

        # Record restart
        restart_data[profile].append(time.time())
        save_restart_log(restart_data)
        return True
    except Exception as e:
        log(f"     ❌ 重启失败: {e}")
        return False

def mark_state_dead(profile):
    """Layer 9: State实时化 — PID死亡时标记平台为disconnected"""
    state_path = f"D:/hermes/hermes-data/profiles/{profile}/gateway_state.json"
    if not os.path.exists(state_path):
        return
    try:
        with open(state_path, encoding="utf-8-sig") as f:
            d = json.load(f)
        modified = False
        if "platforms" in d:
            for name in list(d["platforms"].keys()):
                if d["platforms"][name].get("state") == "connected":
                    d["platforms"][name]["state"] = "disconnected"
                    d["platforms"][name]["error_message"] = "PID死亡(看门狗标记)"
                    modified = True
        if modified:
            with open(state_path, "w") as f:
                json.dump(d, f, indent=2)
            log(f"     State: 标记 {profile} 全部平台为disconnected")
    except:
        pass

def count_qq_4009(profile):
    """统计QQ Bot 4009断开次数"""
    log_path = f"D:/hermes/hermes-data/profiles/{profile}/logs/gateway.log"
    if not os.path.exists(log_path):
        return 0
    try:
        r = subprocess.run(["grep", "-c", "code=4009", log_path],
                          capture_output=True, text=True, timeout=5)
        return int(r.stdout.strip() or 0)
    except:
        return 0

def test_ilink(profile):
    """iLink API直达检测 — 使用真实token (FIXED: 不再用***)"""
    env_path = f"D:/hermes/hermes-data/profiles/{profile}/.env"
    if not os.path.exists(env_path):
        return None
    with open(env_path) as f:
        token = None
        for line in f:
            if line.startswith("WEIXIN_TOKEN=") and not line.startswith("#WEIXIN_TOKEN="):
                token = line.split("=", 1)[1].strip()
                break
    if not token:
        return None
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "6",
             "-H", f"Authorization: Bearer {token}",
             "-H", "Content-Type: application/json",
             "-d", '{"get_updates_buf":""}',
             "https://ilinkai.weixin.qq.com/ilink/bot/getupdates"],
            capture_output=True, timeout=8
        )
        resp = r.stdout.decode(errors="replace").strip()
        if '"errcode":-14' in resp or '"ret":-14' in resp:
            return "expired"
        elif '"ret":0' in resp:
            return "ok"
        elif '"ret":' in resp:
            return f"other({resp[:40]})"
        return f"unknown({resp[:40]})"
    except:
        return "timeout"

def check_plugin_activity(profile, platform):
    """检查插件平台最近活动"""
    log_path = f"D:/hermes/hermes-data/profiles/{profile}/logs/gateway.log"
    if not os.path.exists(log_path):
        return "no_log"
    try:
        r = subprocess.run(["grep", platform, log_path], capture_output=True, text=True, timeout=5)
        lines = r.stdout.strip().split("\n")
        if lines and lines[0]:
            last = lines[-1][:60]
            return f"active({last})"
        return "inactive"
    except:
        return "error"

def check_dingtalk_messages(profile):
    """S3: 检查钉钉消息流"""
    log_path = f"D:/hermes/hermes-data/profiles/{profile}/logs/gateway.log"
    if not os.path.exists(log_path):
        return "no_log"
    try:
        r = subprocess.run(
            ["grep", "-c", "platform=dingtalk"],
            capture_output=True, text=True, timeout=5,
            input=subprocess.run(["tail", "-500", log_path], capture_output=True, text=True, timeout=5).stdout
        )
        count = int(r.stdout.strip() or 0)
        return f"{count}条消息" if count > 0 else "无消息"
    except:
        return "unknown"

HOST_STATE = "D:/hermes/hermes-data/gateway_state.json"
HOST_VBS = "D:/hermes/hermes-data/gateway-service/Hermes_Gateway_76bff4d2.vbs"

def host_state():
    """0.21.5 MULTIPLEX: ONE host gateway (default profile) serves every profile.
    Per-profile gateway_state.json files are legacy; their pid may be 0 or a dead
    value while the profile is perfectly served by the host gateway."""
    try:
        with open(HOST_STATE, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}

def host_gateway_up():
    return check_pid(host_state().get("pid", 0) or 0)

def host_profile_platforms(name):
    """Platform states for one profile, read from the host gateway's state."""
    d = host_state()
    out = {}
    for k, v in d.get("platforms", {}).items():
        if k.startswith(name + ":"):
            out[k.split(":", 1)[1]] = v
        elif ":" not in k and name == "default":
            out[k] = v
    return out

def run():
    log("=" * 55)
    log("看门狗v3.1 全平台健康检查 + 自动修复")
    log("=" * 55)

    alerts = []
    restarts_done = 0

    hst = host_state()
    host_up = check_pid(hst.get("pid", 0) or 0)
    log("  HOST gateway (multiplex): " + ("UP pid=" + str(hst.get("pid")) if host_up else "DOWN"))

    for name in PROFILES:
        state_path = f"D:/hermes/hermes-data/profiles/{name}/gateway_state.json"
        if not os.path.exists(state_path):
            log(f"  {name:8s} ❌ No state file")
            continue

        with open(state_path, encoding="utf-8-sig") as f:
            d = json.load(f)

        pid = d.get("pid", 0) or 0
        alive = check_pid(pid)
        platforms = d.get("platforms", {})
        if host_up:
            hp = host_profile_platforms(name)
            if hp:
                platforms = hp
        updated = d.get("updated_at", "")[:19]

        if not alive and pid > 0 and not host_up:
            mark_state_dead(name)
            log(f"  💀 {name} PID={pid} dead, 自动修复中...")
            if auto_repair(name):
                restarts_done += 1
            else:
                alerts.append(f"{name}: 修复失败(超过重启上限)")
        else:
            issues = []
            for plat, info in platforms.items():
                s = info.get("state", "?")
                if s != "connected" and s not in ["disabled", "stopped"]:
                    issues.append(f"{plat}:{s}")

            ilink = None if host_up else test_ilink(name)
            if ilink == "expired":
                issues.append("微信session过期")
                # W3: 自动QR认证
                if name == "qqbot3":
                    log(f"  📱 {name}: 微信过期, 触发自动QR认证")
                    try:
                        import ssl, urllib.request, qrcode
                        tok = None
                        with open(f"D:/hermes/hermes-data/profiles/{name}/.env") as f:
                            for line in f:
                                if line.startswith("WEIXIN_TOKEN=") and not line.startswith("#"):
                                    tok = line.split("=", 1)[1].strip()
                                    break
                        if tok:
                            ctx = ssl._create_unverified_context()
                            data = json.loads(urllib.request.urlopen(
                                urllib.request.Request("https://ilinkai.weixin.qq.com/ilink/bot/get_bot_qrcode?bot_type=3",
                                    headers={"Authorization": f"Bearer {tok}"}),
                                context=ctx, timeout=15).read())
                            qr_url = data.get("qrcode_img_content", "")
                            if qr_url:
                                qr = qrcode.QRCode(version=1, box_size=10, border=3)
                                qr.add_data(qr_url)
                                qr.make(fit=True)
                                qr.make_image(fill_color="black", back_color="white").save(f"D:/hermes/data/wechat_qr_{name}.png")
                                # 【关闭推送-2026-07-26】用户要求关闭微信认证二维码自动推送
                                # 如需恢复，取消注释下面3行
                                # subprocess.run(["hermes", "--profile", name, "send", "-t", "qqbot",
                                #     f"📱 微信认证二维码已生成,请扫描:\\n{qr_url}"], capture_output=True, timeout=10)
                                log(f"     QR已保存到 D:/hermes/data/wechat_qr_{name}.png（推送已禁用）")
                    except Exception as e:
                        log(f"     QR生成失败: {e}")

            qq9 = 0 if host_up else count_qq_4009(name)
            if qq9 > 5:
                issues.append(f"QQ 4009×{qq9}")

            if name == "mybot" and not host_up:
                dt = check_plugin_activity(name, "dingtalk")
                if "inactive" in dt:
                    issues.append("钉钉无活动")
                dt_msgs = check_dingtalk_messages(name)
                issues.append(f"钉钉消息:{dt_msgs}" if "无消息" in dt_msgs else f"钉钉:{dt_msgs}")

        # Determine real status
        if not alive and pid > 0:
            real = "dead"
        else:
            real = "healthy" if not issues else "degraded"

        icon = {"healthy": "✅", "dead": "💀", "degraded": "🟡"}.get(real, "❓")
        plats = " ".join(f"{k}:{v['state']}" for k,v in platforms.items()) if platforms else "(no platforms)"
        log(f"  {icon} {name:8s} PID={pid:<6} alive={str(alive):5}  {plats}")
        if issues:
            log(f"      ⚠ {', '.join(issues[:3])}")
            alerts.append(f"{name}: {', '.join(issues[:2])}")
        else:
            log(f"      ✅ All good")

    if alerts:
        log(f"\n⚠ ALERTS ({len(alerts)}):")
        for a in alerts:
            log(f"  • {a}")
    else:
        log("\n✅ 全部正常")

    if restarts_done:
        log(f"\n🔄 本次巡检自动重启 {restarts_done} 个gateway")

    restart_data = load_restart_log()
    for p in restart_data:
        restart_data[p] = clean_old_restarts(restart_data[p])
    save_restart_log(restart_data)

if __name__ == "__main__":
    run()
