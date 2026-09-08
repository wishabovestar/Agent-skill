# -*- coding: utf-8 -*-
"""混合代理守护 v1.0 (2026-09-07)
8800 local_first_mixer 存活守护 — 死则拉起 (带冷却限次防崩溃循环)
参考: gateway_health_check.py 模式 (零 LLM token)

输出: [MIXER-GUARD-OK] 健康 (静默 — cron no_agent 不扰)
      异常时输出详情 (拉起成功/失败)
"""
# side_effects: [拉进程, 写状态]
import json, os, subprocess, time, datetime, sys

MIXER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_first_mixer.py")
PY = sys.executable
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mixer_guard_state.json")
URL = "http://127.0.0.1:8800/health"   # 2026-09-08 修复: 原 /v1/models 不存在 → 404 误判死 → 反复拉起+双实例乱象 (9-7 实证)
COOLDOWN = 600   # 拉起后冷却 (秒) — 防循环
MAX_FAIL = 3     # 连续失败超限 → 停手告警 (防崩溃风暴)


def mixer_alive():
    """8800 健康探测 (2s 超时)"""
    import urllib.request
    try:
        urllib.request.urlopen(URL, timeout=2)
        return True
    except Exception:
        return False


def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}


def save_state(s):
    json.dump(s, open(STATE, "w", encoding="utf-8"))


def main():
    st = load_state()
    now = time.time()
    if mixer_alive():
        # 健康: 重置失败计数 (仅记录恢复)
        if st.get("fails", 0) > 0:
            st["fails"] = 0
            st["recovered_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_state(st)
            print(f"[MIXER-GUARD] 8800 已恢复 (上次拉起后稳定)")
        return  # 静默 — OK

    # 死 → 冷却检查
    last_launch = st.get("last_launch", 0)
    if now - last_launch < COOLDOWN:
        print(f"[MIXER-GUARD] 8800 仍死 (冷却中 — 上次拉起 {int(now-last_launch)}s 前)")
        return
    if st.get("fails", 0) >= MAX_FAIL:
        print(f"[MIXER-GUARD-ERR] 连续失败 {st['fails']} 次超限 — 停手待人工 (mixer 可能配置坏)")
        return

    # 拉起 (独立进程 — 脱离本会话)
    try:
        subprocess.Popen([PY, "-X", "utf8", MIXER],
                         cwd=os.path.dirname(MIXER),
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                         | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        st["fails"] = st.get("fails", 0) + 1
        st["last_launch"] = now
        st["last_attempt"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_state(st)
        print(f"[MIXER-GUARD] 8800 死 — 已拉起 (尝试 {st['fails']}/{MAX_FAIL})")
    except Exception as e:
        print(f"[MIXER-GUARD-ERR] 拉起失败: {e}")


if __name__ == "__main__":
    main()
