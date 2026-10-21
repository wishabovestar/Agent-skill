#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memos_embed_patch_watchdog.py —— MemOS「向量源 summary 优先」补丁的巡检 + 自动重打。

背景：修法改的是 node_modules/@memtensor/memos-local-plugin/dist/*.js ⇒ **npm 重装即失效**。
本脚本按 cron 反复巡检，发现被打回原样就立刻重打并**出声**（stdout 非空 ⇒ Hermes 才会通知）。

纪律（Hermes cron no_agent 脚本）：
  * 必须 .py（调度器用自己的解释器跑；.sh 会被 bash 吃掉反斜杠）；
  * **stdout 空 ⇒ 不通知**（健康时不打扰）。

退出码：0 = 健康或已自动修复；1 = 异常（需要人看）。
"""
import subprocess
import sys
import os

PATCHER = r"D:/hermes/analysis/memory_ab/patch_memos_embedding_source.py"
PY = sys.executable


def run(*args):
    p = subprocess.run([PY, PATCHER, *args], capture_output=True, text=True,
                       timeout=120, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main():
    rc, out = run("--check")
    if rc == 0:
        return 0                      # 全已修 ⇒ stdout 空 ⇒ 静默
    tail = "\n".join(l for l in out.strip().splitlines()[-4:])
    # 有未修/异常 ⇒ 自动重打
    rc2, out2 = run("--apply")
    rc3, out3 = run("--check")
    lines = [l for l in out3.strip().splitlines() if l.startswith("[")]
    print(f"[memos-embed-patch] 巡检发现补丁失效 ⇒ 已自动重打；apply_exit={rc2} check_exit={rc3}")
    print(f"  发现时快照: {tail}")
    for l in lines:
        print("  " + l)
    if rc3 != 0:
        print("  ❌ 自动重打后仍未全绿 ⇒ 需要人工介入（版本变了？）")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
