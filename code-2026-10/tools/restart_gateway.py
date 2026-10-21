#!/usr/bin/env python3
"""独立进程重启Hermes gateway - 通过cmd start完全脱离gateway进程树"""
import subprocess, sys, os, time

# 用 Windows API 创建完全独立的进程
cmd = 'hermes gateway restart > D:/hermes/data/gateway_restart.log 2>&1'

# CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW | DETACHED_PROCESS
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
flags = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW | DETACHED_PROCESS

try:
    proc = subprocess.Popen(
        ['cmd.exe', '/c', cmd],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )
    print(f"✅ 已启动独立重启进程 PID={proc.pid}")
    print("等待10秒后检查日志...")
    time.sleep(10)
    if os.path.exists(r'D:/hermes/data/gateway_restart.log'):
        with open(r'D:/hermes/data/gateway_restart.log', encoding='utf-8', errors='ignore') as f:
            print("=== 重启日志 ===")
            print(f.read()[-2000:])
    else:
        print("日志尚未生成，重启可能在后台继续")
except Exception as e:
    print(f"❌ 启动失败: {e}")
