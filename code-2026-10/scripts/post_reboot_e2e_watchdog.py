#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""cron 看门狗 shim —— 把 stdout 原样透传（空 ⇒ 不推送）。

真正的跑手：D:/hermes/analysis/memory_ab/post_reboot_e2e.py
（Hermes cron 的 no_agent 脚本路径必须在 profile 的 scripts/ 下 ⇒ 用本 shim 转发；
  用 .py 而非 .sh：调度器用自己的解释器跑 .py，.sh 会被 bash 吃反斜杠。）
"""
import subprocess
import sys

REAL = r"D:/hermes/analysis/memory_ab/post_reboot_e2e.py"
PY = r"C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"

p = subprocess.run([PY, "-u", REAL], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=5400)
out = (p.stdout or "") + (p.stderr or "")

# ⚠️ cron 的 no_agent 模式：**非零退出会发错误告警**。
#    跑手用 3=GPU 未就绪（应当静默）、0=完成、4/5=前置/真跑受阻（本身已印原因）。
#    ⇒ 一律映射为 exit 0，让「有没有输出」成为唯一通知开关；只在**无任何输出**时才补一行诊断（失败出声）。
if out.strip():
    sys.stdout.write(out if out.endswith("\n") else out + "\n")
elif p.returncode not in (0, 3):
    sys.stdout.write(
        f"[post_reboot_e2e] 跑手以 exit={p.returncode} 退出但无输出（非 GPU 未就绪）⇒ 请查 "
        f"D:/hermes/analysis/memory_ab/logs/post_reboot_e2e_*.log\n")
sys.exit(0)
