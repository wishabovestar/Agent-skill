#!/usr/bin/env python3
"""
browser-act Hermes wrapper
自动检测/设置Python 3.12环境, 运行browser-act CLI
"""
import sys, os, subprocess, shutil, json
from pathlib import Path

PY312_DIR = Path.home() / "AppData/Local/hermes/envs/py312"
PIP_CACHE = Path.home() / "AppData/Local/hermes/cache/pip"

def log(msg):
    print(f"[browser-act-wrapper] {msg}", file=sys.stderr)

def find_python312():
    # 检查已知位置
    candidates = [
        PY312_DIR / "python.exe",
        Path("D:/Program Files/Python312/python.exe"),
        Path.home() / "AppData/Local/Programs/Python/Python312/python.exe",
        Path.home() / "AppData/Local/Microsoft/WindowsApps/python3.12.exe",
    ]
    for c in candidates:
        if c.exists():
            return c
    # 检查PATH
    which = shutil.which("python3.12") or shutil.which("python3.12.exe")
    if which:
        return Path(which)
    return None

def ensure_env():
    py = find_python312()
    if py:
        log(f"使用Python 3.12: {py}")
        return py

    log("Python 3.12 未安装, 尝试通过uv安装...")
    # 尝试通过uv安装
    result = subprocess.run(
        ["uv", "python", "install", "3.12.13"],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode == 0:
        # 找到新安装的Python
        r2 = subprocess.run(
            ["uv", "python", "find", "3.12"],
            capture_output=True, text=True
        )
        if r2.returncode == 0:
            py_path = r2.stdout.strip()
            if py_path:
                log(f"uv安装Python 3.12成功: {py_path}")
                return Path(py_path)

    log("⚠ Python 3.12 不可用. 请手动安装: uv python install 3.12")
    log("   或从 python.org 下载 Python 3.12.13 安装")
    return None

def main():
    if len(sys.argv) < 2:
        print("用法: browser-act-wrapper <browser-act参数...>", file=sys.stderr)
        sys.exit(1)

    # 确保Python 3.12环境
    py = find_python312()
    if not py:
        py = ensure_env()

    if not py:
        print("ERROR: Python 3.12 required for browser-act", file=sys.stderr)
        print("Install: uv python install 3.12", file=sys.stderr)
        sys.exit(1)

    # 检查browser-act-cli是否在py312环境中安装
    check = subprocess.run(
        [str(py), "-m", "pip", "list", "--format=json"],
        capture_output=True, text=True, timeout=30
    )
    installed = []
    if check.returncode == 0:
        installed = [p["name"] for p in json.loads(check.stdout)]

    if "browser-act-cli" not in installed:
        log("安装 browser-act-cli 到 Python 3.12 环境...")
        wheel = Path("C:/Users/Administrator/AppData/Local/Temp/browser_act_cli-1.1.0-py3-none-any.whl")
        if wheel.exists():
            install = subprocess.run(
                [str(py), "-m", "pip", "install", str(wheel)],
                capture_output=True, text=True, timeout=120
            )
            if install.returncode != 0:
                log(f"安装失败: {install.stderr}")
                # fallback: 从PyPI安装
                install2 = subprocess.run(
                    [str(py), "-m", "pip", "install", "browser-act-cli"],
                    capture_output=True, text=True, timeout=120
                )
                if install2.returncode != 0:
                    log(f"PyPI安装也失败: {install2.stderr}")
                    sys.exit(1)

    # 运行browser-act
    cmd = [str(py), "-m", "browser_act_cli"] + sys.argv[1:]
    log(f"运行: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
