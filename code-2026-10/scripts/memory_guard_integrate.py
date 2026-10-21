# -*- coding: utf-8 -*-
"""memory_guard 接入记忆写入流 v1.0 (2026-08-10)
Hermes /memory 审批前 → memory_guard 检测 → 标记风险

接入点: write_approval 流程前加 guard 检查
落地: 提供 CLI 供 agent 审批时调用 + 扫描 pending 记忆

用法:
  python memory_guard_integrate.py check_pending   # 扫描待审批记忆
  python memory_guard_integrate.py verify <text>   # 单条验证
"""
import os, sys, io, json, time, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memory_guard import check, protect

# Hermes 记忆存储位置
MEMORY_FILES = [
    r"D:\hermes\hermes-data\profiles\qqbot3\memories\MEMORY.md",
    r"D:\hermes\hermes-data\profiles\qqbot3\memories\USER.md",
    r"D:\hermes\hermes-data\profiles\qqbot3\memories\pending.md",
]

def scan_pending():
    """扫描 pending/新记忆 → 检测注入"""
    print("=== Memory Guard: 待审批记忆扫描 ===\n")
    found_issues = 0
    for f in MEMORY_FILES:
        if not os.path.exists(f):
            continue
        content = open(f, encoding="utf-8").read()
        # 按行/段检测
        for line in content.split("\n"):
            line = line.strip()
            if len(line) < 10:
                continue
            result = check(line, "memory_file")
            if result["risk_level"] in ("high", "medium"):
                found_issues += 1
                print(f"⚠️ [{f.split(chr(92))[-1]}] {result['risk_level']}: {line[:60]}")
                print(f"   发现: {result['findings']}")
    if found_issues == 0:
        print("✅ 无风险记忆条目")
    else:
        print(f"\n⚠️ {found_issues} 条风险记忆 — 建议隔离")
    return found_issues

def verify(text):
    """单条验证 (agent 审批时调用)"""
    result = check(text, "memory_file")
    print(f"🔍 验证: {result['risk_level']} → {result['action']}")
    if result["findings"]:
        print(f"   发现: {result['findings']}")
    return result

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "verify":
        verify(sys.argv[2])
    else:
        scan_pending()
