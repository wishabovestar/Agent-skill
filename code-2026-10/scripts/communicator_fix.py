#!/usr/bin/env python3
"""
通联-平台健康检查 v2 定时执行包装器
在 cron 中以 no-agent 模式运行，调用 communicator.py --fix

用法: python communicator_fix.py
"""
import subprocess
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COMMUNICATOR = os.path.join(SCRIPT_DIR, "communicator.py")

if __name__ == "__main__":
    result = subprocess.run(
        [sys.executable, COMMUNICATOR, "--fix"],
        capture_output=True, text=True, timeout=120
    )
    # 打印 stdout/stderr 供 cron 捕获
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    sys.exit(result.returncode)
