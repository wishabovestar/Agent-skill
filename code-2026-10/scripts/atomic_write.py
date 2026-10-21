#!/usr/bin/env python3
"""
原子写入工具 — 借鉴 nanobot design.md 原则3/4 (atomic writes, explicit)
=======================================================================
nanobot design.md 核心原则: "Atomic Session Writes" 
  temp文件 + fsync + rename + 目录fsync = 崩溃安全写 (防. 部分写入损坏)

Hermes 现状: 记忆/审计用普通 open(...,"w") — 崩溃可能留下半写文件
本工具: 提供原子写封装, 兼容 OSError/replace, 备份保留

实现 (对齐 nanobot gotchas.md):
  tempfile 同目录写
  fsync (刷到磁盘)
  os.replace (原子替换)
  目录 fsync (持久化rename)
"""
import os, sys, json, tempfile

def atomic_write(path, content, backup=False, encoding="utf-8"):
    """原子写入文件 (temp+fsync+replace+dirfsync)
    Args:
        path: 目标文件路径
        content: str 内容
        backup: 是否保留 .bak 备份 (Hermes可回滚理念)
    Returns: str 实际写入路径
    """
    path = os.path.abspath(path)
    d = os.path.dirname(path)
    # 确保目录存在
    os.makedirs(d, exist_ok=True)

    # backup (保留前版, 可回滚)
    if backup and os.path.exists(path):
        import shutil
        bak = path + ".bak"
        try:
            shutil.copy2(path, bak)
        except Exception:
            pass  # backup失败不阻塞主写

    # 原子写: temp同目录 + fsync + replace
    fd, tmp_path = tempfile.mkstemp(dir=d, prefix=".atomic_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())     # 1. 数据落盘
        os.replace(tmp_path, path)   # 2. 原子替换
        # 3. 目录fsync (持久化rename) — Windows不支持O_DIRECTORY, 跳过
        if hasattr(os, "O_DIRECTORY"):
            try:
                dfd = os.open(d, os.O_DIRECTORY)
                try:
                    os.fsync(dfd)
                finally:
                    os.close(dfd)
            except OSError:
                pass
        return path
    except Exception:
        # 失败清理temp
        try:
            if os.path.exists(tmp_path): os.unlink(tmp_path)
        except OSError: pass
        raise

def atomic_write_json(path, obj, backup=False):
    """原子写 JSON"""
    return atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2), backup=backup)

if __name__ == "__main__":
    # 自我验证
    print("="*50)
    print("原子写入工具 验证")
    print("="*50)
    test = "D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/atomic_write_test.txt"
    # 写第1版
    r = atomic_write(test, "version1\n", backup=True)
    print(f"✅ 写v1: {r}")
    # 写第2版 (backup保留v1)
    r2 = atomic_write(test, "version2\n", backup=True)
    print(f"✅ 写v2: {r2} (backup保留前版)")
    # JSON原子写
    j = atomic_write_json("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/atomic_test.json",
                          {"engine":"atomic","atomic":True}, backup=True)
    print(f"✅ 写JSON: {j}")
    # 检查 .bak
    b = test + ".bak"
    if os.path.exists(b):
        print(f"✅ 备份存在: {os.path.basename(b)} (内容={open(b).read().strip()})")
    # 清理
    os.remove(test)
    for f in [test+".bak", "D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/atomic_test.json",
              "D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/atomic_test.json.bak"]:
        if os.path.exists(f): os.remove(f)
    print("✅ 验证完成, 已清理测试文件")
