# -*- coding: utf-8 -*-
"""CortexMem 每日巩固 cron 入口 (2026-08-15)
修复: Hermes cron scheduler 的 script 字段不支持带参数 (整串当作文件名),
因此 cron_guard.py --task ... 直接报 "Script not found"。

本包装器把参数固化, 供 scheduler 以纯文件名调用:
  cortexmem_daily_guard.py
内部链: cron_guard(超时挂起/blocked 标记) → cron_reversible_wrap(快照+意外修改回滚) → cortexmem_daily.py
所有路径用绝对路径, 不依赖 cwd (scheduler 以 scripts/ 为 cwd 运行)。
"""
# side_effects: [无写入, 输出]
import os
import subprocess
import sys

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(SCRIPTS, "cron_guard.py")
WRAP = os.path.join(SCRIPTS, "cron_reversible_wrap.py")
DAILY = os.path.join(SCRIPTS, "cortexmem_daily.py")

# cron_guard 内部用 shell=True 执行 --cmd, 故 cmd 保持字符串形式 (路径带引号防空格)
inner_cmd = '"%s" "%s" "%s"' % (sys.executable, WRAP, DAILY)

argv = [
    sys.executable, GUARD,
    "--task", "CortexMem每日巩固",
    "--cmd", inner_cmd,
    "--timeout", "400",
]
sys.exit(subprocess.call(argv, cwd=SCRIPTS))
