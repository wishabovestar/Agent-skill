# -*- coding: utf-8 -*-
"""CortexMem 备份轮转 (R1097) — 保留最近 N 份, 旧的压缩归档

★ 动机: 8 份 state.json 备份堆积 143MB (state.json 本身仅 23MB)
★ 策略: 保留最近 3 份 (含 .bak) + 其余压缩为 tar.gz 归档
"""
# side_effects: [移动/压缩文件]
import glob
import os
import shutil
import sys
import tarfile
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMDIR = os.path.join(BASE, "knowledge_base", "cortexmem")
ARCHIVE_DIR = r"D:\hermes\data\cortexmem_backups"
KEEP = 3


def main(apply=False):
    files = glob.glob(os.path.join(CMDIR, "state.json.*"))
    files = [f for f in files if os.path.isfile(f)]
    files.sort(key=os.path.getmtime, reverse=True)

    print("=" * 68)
    print("  CortexMem 备份轮转 (R1097)")
    print("=" * 68)
    print("  目录: %s" % CMDIR)
    print("  备份数: %d | 保留: %d 份" % (len(files), KEEP))
    print()
    total = sum(os.path.getsize(f) for f in files)
    print("  备份总占用: %.1f MB" % (total / 1e6))
    print()

    keep = files[:KEEP]
    old = files[KEEP:]

    print("  ▶ 保留 (最近 %d 份):" % KEEP)
    for f in keep:
        mt = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%m-%d %H:%M")
        print("     %6.1f MB  %s  %s" % (
            os.path.getsize(f) / 1e6, mt, os.path.basename(f)))

    if not old:
        print()
        print("  ✅ 无需归档")
        return

    print()
    print("  ▶ 归档 (%d 份):" % len(old))
    for f in old:
        mt = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%m-%d %H:%M")
        print("     %6.1f MB  %s  %s" % (
            os.path.getsize(f) / 1e6, mt, os.path.basename(f)))

    if not apply:
        print()
        print("  ⚪ dry-run (未执行). 加 --apply 实际归档")
        print("  ★ 预计释放: %.1f MB" % (sum(os.path.getsize(f) for f in old) / 1e6))
        return

    # 实际归档
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    out = os.path.join(ARCHIVE_DIR,
                       "cortexmem_state_backups_%s.tar.gz"
                       % datetime.now().strftime("%Y%m%d_%H%M%S"))
    with tarfile.open(out, "w:gz") as tar:
        for f in old:
            tar.add(f, arcname=os.path.basename(f))
    print()
    print("  ✅ 已归档 → %s" % out)
    print("     归档大小: %.1f MB (压缩自 %.1f MB)" % (
        os.path.getsize(out) / 1e6,
        sum(os.path.getsize(f) for f in old) / 1e6))

    # ★ 验证归档可读再删
    try:
        with tarfile.open(out, "r:gz") as tar:
            n = len(tar.getnames())
            # 抽查第一个成员可读
            member = tar.getmembers()[0]
            data = tar.extractfile(member).read(1024)
        print("     ★ 归档校验: %d 个成员, 首个成员可读 (%d 字节) ✅" % (n, len(data)))
        if n != len(old):
            print("     🔴 成员数不符! 【不删除】源文件")
            return
    except Exception as e:
        print("     🔴 归档校验失败: %s 【不删除】源文件" % str(e)[:80])
        return

    # 删除已归档的
    freed = 0
    for f in old:
        sz = os.path.getsize(f)
        os.remove(f)
        freed += sz
    print("     ✅ 已删除 %d 份源文件, 释放 %.1f MB" % (len(old), freed / 1e6))


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
