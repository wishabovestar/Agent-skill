#!/usr/bin/env python3
"""
Redis 修复与重启脚本 — 确保 Redis 使用 .env 中的密码启动

使用:
  python3 redis_fix.py               # 诊断
  python3 redis_fix.py --fix         # 修复 (重启Redis)
  python3 redis_fix.py --status      # 状态检查
"""

import os, sys, json, re, time, subprocess, socket
from pathlib import Path

HERMES_HOME = Path.home() / "AppData/Local/hermes"
PROFILE_DIR = HERMES_HOME / "profiles" / "mybot"
REDIS_DIR = Path.home() / "redis"
ENV_FILE = PROFILE_DIR / ".env"
REDIS_CONF = REDIS_DIR / "hermes_redis.conf"

def get_password_from_env():
    """从 .env 读取密码"""
    if not ENV_FILE.exists():
        print("✗ .env not found")
        return None
    content = ENV_FILE.read_text(encoding="utf-8")
    m = re.search(r'REDIS_PASSWORD=([^\n\r]+)', content)
    if m:
        pw = m.group(1).strip().strip("'\"")
        return pw
    print("✗ REDIS_PASSWORD not in .env")
    return None

def get_redis_pid():
    """查找 Redis 进程"""
    try:
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq redis-server.exe", "/FO", "CSV"],
            capture_output=True, timeout=5
        )
        output = r.stdout.decode("gbk", errors="replace")
        for line in output.splitlines():
            if "redis-server" in line and "PID" not in line:
                parts = line.split(",")
                if len(parts) >= 2:
                    return int(parts[1].strip().strip('"'))
    except Exception as e:
        print(f"  tasklist error: {e}")
    return None

def test_connection(password, host="127.0.0.1", port=6379):
    """测试 Redis 连接"""
    try:
        import sys as _sys
        # 尝试使用 Hermes venv 的 Python
        hermes_py = HERMES_HOME / "hermes-agent" / "venv" / "Scripts" / "python.exe"
        if hermes_py.exists():
            code = f"""
import redis
r = redis.Redis(host='{host}', port={port}, db=0, 
                password='{password}', socket_connect_timeout=3)
r.ping()
info = r.info()
print(f'OK|version={{info.get(\"redis_version\",\"?\")}}|keys={{r.dbsize()}}|memory={{info.get(\"used_memory_human\",\"?\")}}')
"""
            r = subprocess.run([str(hermes_py), "-c", code], capture_output=True, timeout=10)
            output = r.stdout.decode().strip()
            if output.startswith("OK|"):
                parts = output.split("|")
                return {"ok": True, "version": parts[1].split("=")[1], 
                        "keys": parts[2].split("=")[1], "memory": parts[3].split("=")[1]}
            err = r.stderr.decode().strip()
            if "invalid password" in err:
                return {"ok": False, "error": "invalid_password"}
            if "Authentication required" in err:
                return {"ok": False, "error": "auth_required"}
            return {"ok": False, "error": err[:100]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}

def start_redis(password):
    """启动 Redis 带密码"""
    import subprocess as _sp
    
    # 查找 redis-server.exe
    redis_exe = REDIS_DIR / "redis-server.exe"
    if not redis_exe.exists():
        # 尝试 PATH
        r = _sp.run(["where", "redis-server"], capture_output=True, timeout=5)
        path = r.stdout.decode().strip()
        if path:
            redis_exe = Path(path.splitlines()[0])
        else:
            print("✗ redis-server.exe not found")
            return False
    
    # 准备配置
    data_dir = HERMES_HOME / "redis_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    log_dir = HERMES_HOME / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    conf_lines = [
        "bind 127.0.0.1",
        "port 6379",
        f"requirepass {password}",
        "rename-command FLUSHALL \"\"",
        "rename-command FLUSHDB \"\"",
        "rename-command CONFIG \"\"",
        "rename-command SHUTDOWN \"\"",
        "rename-command DEBUG \"\"",
        "rename-command SCRIPT \"\"",
        "save 900 1",
        "save 300 10",
        "save 60 10000",
        "rdbcompression yes",
        f"dbfilename hermes_cache.rdb",
        f"dir {data_dir}",
        f"logfile {log_dir / 'redis.log'}",
        "databases 16",
        "timeout 300",
        "tcp-keepalive 60",
        "maxmemory 512mb",
        "maxmemory-policy allkeys-lru",
        "loglevel notice",
    ]
    
    # 写入临时配置
    tmp_conf = REDIS_DIR / "redis_active.conf"
    tmp_conf.write_text("\n".join(conf_lines) + "\n", encoding="utf-8")
    
    # 用 DETACHED_PROCESS 启动
    DETACHED = _sp.CREATE_NEW_PROCESS_GROUP | _sp.DETACHED_PROCESS
    try:
        p = _sp.Popen(
            [str(redis_exe), str(tmp_conf)],
            creationflags=DETACHED,
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, stdin=_sp.DEVNULL,
        )
        print(f"  Started Redis (PID will be assigned)...")
        return True
    except Exception as e:
        print(f"✗ Start failed: {e}")
        return False

def kill_redis():
    """杀死 Redis 进程"""
    pid = get_redis_pid()
    if not pid:
        print("  No Redis process found")
        return True
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], 
                      capture_output=True, timeout=5)
        print(f"  Killed Redis PID {pid}")
        time.sleep(2)
        return True
    except Exception as e:
        print(f"✗ Kill failed: {e}")
        return False

def diagnose():
    """完整诊断"""
    print("=" * 50)
    print("Redis 诊断报告")
    print("=" * 50)
    
    # 进程状态
    pid = get_redis_pid()
    if pid:
        print(f"\n✓ Redis 进程: PID {pid}")
    else:
        print(f"\n✗ Redis 未运行")
    
    # 密码
    pw = get_password_from_env()
    if pw:
        print(f"✓ .env 密码: {pw[:4]}...{pw[-4:]} ({len(pw)} chars)")
    else:
        print(f"✗ .env 无密码")
        return
    
    # 连接测试
    if pid and pw:
        result = test_connection(pw)
        if result.get("ok"):
            print(f"✓ 连接成功: v{result['version']}, {result['keys']} keys, {result['memory']}")
        elif result.get("error") == "invalid_password":
            print(f"✗ 密码不匹配 — Redis 配置的密码与 .env 不同")
            print(f"  需要重启 Redis 以使用正确的密码")
        elif result.get("error") == "auth_required":
            print(f"✗ Redis 需要密码但未提供")
        else:
            print(f"✗ 连接失败: {result.get('error')}")
    
    # 已保存的 keys (通过 info)
    if pid:
        try:
            # 尝试无密码探测
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(("127.0.0.1", 6379))
            sock.sendall(b"PING\r\n")
            resp = sock.recv(1024)
            sock.close()
            if b"NOAUTH" in resp:
                print("  Redis 状态: 需认证")
            elif b"PONG" in resp:
                print("  Redis 状态: 无密码运行")
            else:
                print(f"  Redis 响应: {resp[:50]}")
        except Exception as e:
            print(f"  Socket探测失败: {e}")

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "diagnose"
    
    if action in ("--status", "--diagnose", "-s"):
        diagnose()
        return
    
    if action in ("--fix", "-f"):
        print("\n🔄 修复 Redis...")
        pw = get_password_from_env()
        if not pw:
            print("✗ 无法获取密码，终止")
            return
        
        # 停止旧 Redis
        kill_redis()
        time.sleep(1)
        
        # 启动新 Redis
        if start_redis(pw):
            time.sleep(2)
            # 验证
            result = test_connection(pw)
            if result.get("ok"):
                print(f"✓ Redis 已修复并运行: v{result['version']}")
            else:
                print(f"✗ Redis 启动但验证失败: {result}")
        return
    
    if action in ("--kill", "-k"):
        kill_redis()
        return
    
    print(f"用法: python3 redis_fix.py [--diagnose|--fix|--kill]")

if __name__ == "__main__":
    main()
