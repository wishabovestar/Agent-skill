"""重启 mybot gateway — 完全脱离gateway进程树 (复用之前验证过的方案)"""
import subprocess, os, time

HERMES_EXE = r"C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe"
PROFILE = "mybot"
LOG_FILE = r"D:/hermes/data/gateway_restart.log"

def restart_gateway():
    # 1. 停止旧gateway
    print("[1/3] 停止旧gateway...")
    subprocess.run([HERMES_EXE, "--profile", PROFILE, "gateway", "stop"],
                   capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(3)

    # 2. 启动新gateway (DETACHED)
    print("[2/3] 启动新gateway...")
    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    with open(LOG_FILE, "w") as logf:
        subprocess.Popen(
            [HERMES_EXE, "--profile", PROFILE, "gateway", "run", "--replace"],
            stdout=logf, stderr=logf, stdin=subprocess.DEVNULL,
            creationflags=flags, close_fds=True
        )
    time.sleep(5)

    # 3. 验证
    print("[3/3] 验证gateway...")
    try:
        r = subprocess.run([HERMES_EXE, "--profile", PROFILE, "gateway", "status"],
                           capture_output=True, timeout=15, text=True, encoding='utf-8', errors='replace')
        print("Status:", r.stdout.strip()[:200] or r.stderr.strip()[:200])
    except Exception as e:
        print(f"status检查: {e}")

if __name__ == "__main__":
    restart_gateway()
