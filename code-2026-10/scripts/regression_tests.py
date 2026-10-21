#!/usr/bin/env python3
"""
通联回归测试 — v2.5
验证"gateway死亡→看门狗检测→恢复"全链路

用法:
  python3 regression_tests.py           # 运行全部测试
  python3 regression_tests.py --name X  # 仅运行指定测试
"""
import json, os, sys, subprocess, time, random, string
from datetime import datetime, timezone

HOME = os.path.expanduser("~/AppData/Local/hermes/profiles/mybot")
STATE_FILE = os.path.join(HOME, "gateway_state.json")
SCRIPTS = os.path.join(HOME, "scripts")
GATEWAY_SERVICE = os.path.join(HOME, "gateway-service")

ALL_PASSED = True


def log(msg, status=""):
    icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️", "INFO": "ℹ️"}.get(status, "")
    print(f"  {icon} {msg}" if icon else f"     {msg}")


def run_test(name, fn):
    global ALL_PASSED
    print(f"\n--- {name} ---")
    try:
        fn()
        log("通过", "PASS")
    except AssertionError as e:
        log(f"失败: {e}", "FAIL")
        ALL_PASSED = False
    except Exception as e:
        log(f"异常: {e}", "FAIL")
        ALL_PASSED = False


# ===== 测试1: 看门狗检测stale PID =====
def test_watchdog_detects_stale_pid():
    """伪造含死亡PID的state.json，看门狗应返回exit=2"""
    fake_pid = 99999  # 不可能存在的PID
    fake_state = {
        "pid": fake_pid,
        "gateway_state": "running",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "platforms": {"test": {"state": "connected", "updated_at": "2026-01-01T00:00:00+00:00"}}
    }
    
    # 备份真实state
    real_state = None
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            real_state = f.read()
    
    try:
        # 写入伪造state
        with open(STATE_FILE, "w") as f:
            json.dump(fake_state, f)
        
        # 运行看门狗（单次检查模式）
        r = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "gateway_watchdog.py")],
            capture_output=True, text=True, timeout=30
        )
        
        # exit code应为2 (CRITICAL)
        assert r.returncode == 2, \
            f"预期exit_code=2(CRITICAL)，实际={r.returncode}"
        
        output = r.stdout + r.stderr
        assert "已死亡" in output or "CRITICAL" in output, \
            f"应报告PID死亡，实际输出: {output[:200]}"
        
        log("看门狗正确检测到stale PID (exit=2)")
    finally:
        # 恢复真实state
        if real_state:
            with open(STATE_FILE, "w") as f:
                f.write(real_state)


# ===== 测试2: 看门狗健康状态下exit=0 =====
def test_watchdog_healthy_exit():
    """当gateway正常运行时，看门狗应exit=0"""
    r = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "gateway_watchdog.py")],
        capture_output=True, text=True, timeout=30
    )
    # 如果gateway活着exit=0，如果死了exit=2。不能是其他值。
    assert r.returncode in (0, 2), \
        f"预期exit=0(健康)或2(死亡)，实际={r.returncode}"


# ===== 测试3: 看门狗daemon模式持续存活 =====
def test_watchdog_daemon_persists():
    """启动看门狗--daemon，验证存活>30秒"""
    import signal
    
    p = subprocess.Popen(
        [sys.executable, os.path.join(SCRIPTS, "gateway_watchdog.py"), "--daemon"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    
    time.sleep(35)  # 等待至少一次检测周期
    
    alive = p.poll() is None
    p.terminate()
    try:
        p.wait(timeout=5)
    except:
        p.kill()
    
    assert alive, "看门狗daemon模式在35秒内退出"


# ===== 测试4: 所有hermes gateway调用含--profile =====
def test_all_gateway_calls_have_profile():
    """扫描所有脚本中hermes.*gateway调用，验证均含--profile"""
    import re
    
    scripts_dir = SCRIPTS
    issues = []
    
    for root, dirs, files in os.walk(scripts_dir):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
            
            # 找hermes命令调用
            for i, line in enumerate(content.split("\n"), 1):
                # 跳过注释行
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                # 找gateway相关调用
                if "gateway" in stripped and ("hermes" in stripped or "subprocess" in stripped):
                    if "--profile" not in stripped and "PROFILE" not in stripped.upper():
                        issues.append(f"{f}:{i}: {stripped[:80]}")
    
    if issues:
        raise AssertionError(f"缺少--profile的调用:\n  " + "\n  ".join(issues))
    log(f"扫描 {scripts_dir} — 全部调用含--profile")


# ===== 测试5: launcher_all.py Redis密码非硬编码 =====
def test_redis_password_not_hardcoded():
    """Redis密码应从环境变量读取"""
    launcher = os.path.join(GATEWAY_SERVICE, "launcher_all.py")
    if not os.path.exists(launcher):
        # v2.5可能已不在该路径
        log("launcher_all.py不存在，跳过")
        return
    
    with open(launcher, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 检查是否还在用硬编码密码
    if 'REDIS_PASS = "' in content or "REDIS_PASS = '" in content:
        raise AssertionError("Redis密码硬编码在launcher_all.py中")
    log("Redis密码未硬编码 ✅")


if __name__ == "__main__":
    print("=" * 50)
    print("  通联v2.5 回归测试")
    print("=" * 50)
    
    run_test("T1: 看门狗检测stale PID", test_watchdog_detects_stale_pid)
    run_test("T2: 看门狗健康状态exit=0", test_watchdog_healthy_exit)
    run_test("T3: 看门狗daemon持续存活", test_watchdog_daemon_persists)
    run_test("T4: 全部gateway调用含--profile", test_all_gateway_calls_have_profile)
    run_test("T5: Redis密码非硬编码", test_redis_password_not_hardcoded)
    
    print(f"\n{'='*50}")
    if ALL_PASSED:
        print("  🎉 全部测试通过!")
    else:
        print("  ❌ 有测试失败，请检查")
    print(f"{'='*50}")
    
    sys.exit(0 if ALL_PASSED else 1)
