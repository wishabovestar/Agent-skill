"""
P3: Tor 代理接入 + 配置
=======================
用于绕过 GFW 访问被屏蔽的国际站点和 .onion 站点。

安装和使用:
  1. winget install TorProject.Tor  (或手动下载安装)
  2. 启动 Tor: tor.exe
  3. 验证: curl --socks5 127.0.0.1:9050 https://check.torproject.org
  4. Hermes 配置: hermes config set web.proxy socks5://127.0.0.1:9050
"""

import subprocess, sys, os, json
from pathlib import Path

CONFIG_FILE = Path.home() / "AppData/Local/hermes/profiles/mybot/config.yaml"
ENV_FILE = Path.home() / "AppData/Local/hermes/profiles/mybot/.env"


def check_tor() -> dict:
    """检查 Tor 安装和运行状态"""
    result = {"installed": False, "running": False, "version": "", "path": ""}

    # 检查安装
    try:
        r = subprocess.run(["where", "tor"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            result["installed"] = True
            result["path"] = r.stdout.strip().split('\n')[0]
    except FileNotFoundError:
        pass

    if not result["installed"]:
        try:
            r = subprocess.run(
                ["curl", "--socks5", "127.0.0.1:9050",
                 "-s", "--max-time", "5",
                 "https://check.torproject.org/api/ip"],
                capture_output=True, timeout=10
            )
            if r.returncode == 0:
                result["installed"] = True
                result["running"] = True
        except:
            pass

    # 检查运行
    if result["installed"]:
        try:
            r = subprocess.run(
                ["curl", "-s", "--max-time", "5",
                 "socks5://127.0.0.1:9050"],
                capture_output=True, timeout=8
            )
            # 如果没报错连接拒绝，认为Tor在运行
            if "Connection refused" not in r.stderr.decode() if r.stderr else True:
                result["running"] = True
        except:
            pass

    # 检查版本
    if result["installed"]:
        try:
            r = subprocess.run(["tor", "--version"], capture_output=True, text=True, timeout=5)
            if r.stdout:
                result["version"] = r.stdout.split('\n')[0].strip()
        except:
            pass

    return result


def install_tor() -> dict:
    """安装 Tor"""
    result = {"success": False, "message": ""}

    # winget 安装
    try:
        r = subprocess.run(
            ["winget", "install", "TorProject.Tor", "--silent", "--accept-package-agreements"],
            capture_output=True, text=True, timeout=120
        )
        if r.returncode == 0:
            result["success"] = True
            result["message"] = "Tor 安装成功 (winget)"
            return result
        result["message"] = f"winget 安装失败: {r.stderr[:100]}"
    except FileNotFoundError:
        result["message"] = "winget 不可用"

    # 手动安装指南
    result["message"] += "\n\n⚠️ 自动安装失败，请手动安装:\n"
    result["message"] += "1. 下载: https://www.torproject.org/download/\n"
    result["message"] += "2. 安装后启动 Tor Browser\n"
    result["message"] += "3. Tor 会监听 127.0.0.1:9150 (Browser) 或 127.0.0.1:9050 (Expert Bundle)\n"
    result["message"] += "4. 配置代理: python setup_tor.py --configure\n"

    return result


def configure_hermes(proxy: str = "socks5://127.0.0.1:9050"):
    """配置 Hermes 使用 Tor 代理"""
    config_path = CONFIG_FILE
    if not config_path.exists():
        return {"success": False, "message": f"Config not found: {config_path}"}

    try:
        content = config_path.read_text(encoding="utf-8")
        lines = content.split('\n')

        # 检查是否已配置
        if any("web.proxy" in l for l in lines):
            return {"success": True, "message": f"代理已配置: {proxy}"}

        # 添加代理配置
        if lines[-1].strip():
            lines.append("")
        lines.append(f"web:")
        lines.append(f"  proxy: {proxy}")
        lines.append(f"  extract_backend: python")  # 使用自定义提取后端

        config_path.write_text('\n'.join(lines), encoding="utf-8")
        return {"success": True, "message": f"代理已配置: {proxy}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def test_tor():
    """测试 Tor 连接"""
    import urllib.request, ssl

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # 通过 Tor 访问
    proxy_handler = urllib.request.ProxyHandler({
        "http": "socks5://127.0.0.1:9050",
        "https": "socks5://127.0.0.1:9050",
    })
    opener = urllib.request.build_opener(proxy_handler)

    for url in ["https://check.torproject.org/",
                 "https://www.bbc.com/news",
                 "https://www.reuters.com"]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = opener.open(req, timeout=10, context=ctx)
            content = resp.read()[:200].decode("utf-8", errors="replace")
            if "congratulations" in content.lower() or "bbc" in content.lower():
                print(f"  ✅ {url} → 可达 (Tor)")
            else:
                print(f"  ⚠️ {url} → {resp.status}")
        except Exception as e:
            print(f"  ❌ {url} → {str(e)[:50]}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--install":
        result = install_tor()
        print(result["message"])
    elif len(sys.argv) > 1 and sys.argv[1] == "--configure":
        proxy = sys.argv[2] if len(sys.argv) > 2 else "socks5://127.0.0.1:9050"
        result = configure_hermes(proxy)
        print(result["message"])
    elif len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_tor()
    else:
        status = check_tor()
        print(f"🧅 Tor 状态")
        print(f"  {'='*30}")
        print(f"  安装: {'✅' if status['installed'] else '❌'} {status.get('version','')}")
        print(f"  运行: {'✅' if status['running'] else '❌'}")
        print(f"  路径: {status.get('path', 'N/A')}")
        print()
        if not status["installed"]:
            print("  安装: python setup_tor.py --install")
        if not status["running"]:
            print("  启动: tor.exe  (或启动 Tor Browser)")
        print("  配置: python setup_tor.py --configure")
        print("  测试: python setup_tor.py --test")
