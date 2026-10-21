"""
Hermes 分割隔离运行引擎 v1.0
为外来代码提供进程级隔离沙盒
"""
import subprocess, sys, json, os, time, hashlib
from pathlib import Path
from datetime import datetime

SANDBOX_ROOT = Path("D:/hermes/sandbox")
AUDIT_LOG = SANDBOX_ROOT / "audit" / "isolation_audit.log"
MAX_TIMEOUT_S = 30

def _log(msg, **extra):
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        extra_str = f" | {json.dumps(extra, ensure_ascii=False)}" if extra else ""
        f.write(f"{datetime.now().isoformat()} [SANDBOX] {msg}{extra_str}\n")

def create_sandbox(source_name):
    """Create isolated sandbox environment"""
    sandbox_id = f"sbox_{hashlib.md5(source_name.encode()).hexdigest()[:8]}"
    sandbox_dir = SANDBOX_ROOT / "active" / sandbox_id
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    info = {"sandbox_id": sandbox_id, "source": source_name, "created_at": datetime.now().isoformat(), "dir": str(sandbox_dir), "status": "created"}
    _log(f"Sandbox created: {source_name}", id=sandbox_id)
    return info

def run_isolated(script_path, input_data=None, timeout=30):
    """Run external code in isolated subprocess. Crash does NOT affect parent."""
    sandbox_id = f"run_{hashlib.md5(script_path.encode()).hexdigest()[:8]}"
    sandbox_dir = SANDBOX_ROOT / "active" / sandbox_id
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", script_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(sandbox_dir),
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        stdout, stderr = proc.communicate(
            input=json.dumps(input_data).encode() if input_data else None, timeout=timeout
        )
        dt = time.time() - t0
        result = {
            "status": "ok" if proc.returncode == 0 else "error",
            "returncode": proc.returncode,
            "stdout_len": len(stdout), "stderr_len": len(stderr),
            "duration": round(dt, 2), "sandbox_id": sandbox_id,
        }
        if proc.returncode != 0:
            _log(f"Subprocess failed", script=script_path, code=proc.returncode)
        return result
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"status": "error", "detail": f"timeout after {timeout}s", "sandbox_id": sandbox_id}
    except Exception as e:
        return {"status": "error", "detail": str(e), "sandbox_id": sandbox_id}

def health_check():
    report = {"sandbox_root": str(SANDBOX_ROOT), "exists": SANDBOX_ROOT.exists(),
              "active_count": len(list((SANDBOX_ROOT / "active").iterdir())) if (SANDBOX_ROOT / "active").exists() else 0}
    try:
        import shutil
        _, _, free = shutil.disk_usage(str(SANDBOX_ROOT))
        report["disk_free_mb"] = free // (1024 * 1024)
    except: pass
    return report

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "health"
    if action == "health":
        print(json.dumps(health_check(), indent=2))
    elif action == "create":
        name = sys.argv[2] if len(sys.argv) > 2 else "unknown"
        print(json.dumps(create_sandbox(name), indent=2))
