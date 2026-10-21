# -*- coding: utf-8 -*-
"""记忆库周度A/B对比 cron 入口 (2026-08-15)
修复: Hermes cron scheduler 的 script 字段不支持带参数 (整串当作文件名)。

本包装器固化参数, 供 scheduler 以纯文件名调用:
  cortexmem_ab_guard.py
内部链: cron_guard(超时挂起/blocked 标记) → cron_reversible_wrap(快照+意外修改回滚) → cortexmem_ab_test.py
所有路径用绝对路径, 不依赖 cwd (scheduler 以 scripts/ 为 cwd 运行)。
"""
# side_effects: [无写入, 输出]
import os
import subprocess
import sys

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(SCRIPTS, "cron_guard.py")
WRAP = os.path.join(SCRIPTS, "cron_reversible_wrap.py")
AB = os.path.join(SCRIPTS, "cortexmem_ab_test.py")

inner_cmd = '"%s" "%s" "%s"' % (sys.executable, WRAP, AB)

argv = [
    sys.executable, GUARD,
    "--task", "记忆库周度A/B",
    "--cmd", inner_cmd,
    "--timeout", "400",
]
sys.exit(subprocess.call(argv, cwd=SCRIPTS))
