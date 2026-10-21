#!/usr/bin/env python3
"""记忆git快照 — 每日03:00自动提交MEMORY/USER到git版本库
用途: nanobot Dream式记忆版本化, 支持diff/回滚/追溯
"""
import shutil, subprocess, sys, os, datetime

MEM_DIR = r"D:\hermes\data\memory_git"
MEM_SRC = r"D:\hermes\hermes-data\profiles\mybot\memories"
FILES = ["MEMORY.md", "USER.md"]

def main():
    changed = False
    # 1. 同步最新记忆文件到git工作区
    for f in FILES:
        src = os.path.join(MEM_SRC, f)
        dst = os.path.join(MEM_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            changed = True
    # 2. git提交 (有变更才提交)
    try:
        r = subprocess.run(["git", "-C", MEM_DIR, "add", "-A"],
                           capture_output=True, text=True, timeout=30)
        r = subprocess.run(["git", "-C", MEM_DIR, "diff", "--cached", "--quiet"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            # 有变更
            date = datetime.datetime.now().strftime("%Y-%m-%d")
            r = subprocess.run(["git", "-C", MEM_DIR, "commit",
                                "-m", f"记忆快照 {date}"],
                               capture_output=True, text=True, timeout=30)
            print(f"✅ 已提交: {r.stdout.strip()[:100]}")
        else:
            print("✅ 无变更, 跳过")
    except Exception as e:
        print(f"❌ git操作失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
