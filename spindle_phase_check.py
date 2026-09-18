# -*- coding: utf-8 -*-
"""纺锤波密度相位验证探针 — V4-SPINDLE 运行解读前先跑本脚本确认密度表。
用法:
  python spindle_phase_check.py           # 输出 4 个 cycle 的相位-密度对照表
  python spindle_phase_check.py 8         # 输出 run #8 对应的 cycle/相位/密度
参数 (与 sleep_spindle_v4.py 保持一致):
  NUM_CYCLES=4, BASE=1.0, HIGH=1.5, DEPTH=0.7
实测基准 (2026-08-17): cycle 0=1.000 (低点) / 1=1.247 (回升) / 2=1.350 (峰值) / 3=1.247 (回落)
"""
import sys, math

NUM_CYCLES = 4
BASE = 1.0
HIGH = 1.5
DEPTH = 0.7

LABELS = {0: "低点", 1: "回升", 2: "峰值", 3: "回落"}


def spindle_density(cycle: int) -> float:
    phase = math.sin(cycle / NUM_CYCLES * math.pi)
    return BASE + (HIGH - BASE) * phase * DEPTH


def main():
    if len(sys.argv) > 1:
        run_count = int(sys.argv[1])
        cycle = run_count % NUM_CYCLES
        print(f"run #{run_count} -> cycle {cycle} ({LABELS[cycle]}) -> density {spindle_density(cycle):.3f}")
    else:
        for c in range(NUM_CYCLES):
            print(f"cycle {c} ({LABELS[c]}): density={spindle_density(c):.3f}")


if __name__ == "__main__":
    main()
