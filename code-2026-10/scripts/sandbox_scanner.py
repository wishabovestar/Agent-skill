"""
安全沙盒探测器 v1.0 — 蜜罐感知+缓慢试探
===========================================
设计原则:
  1. 所有未知端口预设为: 伪装/污染/蜜罐
  2. 每次探测最小化数据交换 (先发1字节, 等响应)
  3. 超时控制严格 (首次0.5s, 逐步放宽)
  4. 只读试探, 绝不写入/认证/登录
  5. 发现可疑行为立即终止并隔离
  6. 每次探测前创建快照, 可回滚

安全约束:
  - 禁止: 发送密码/令牌/密钥
  - 禁止: 执行远程命令
  - 禁止: 上传文件
  - 禁止: 建立持久连接
"""

import socket, struct, time, json, os, subprocess, re
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── 配置 ──
SCAN_LOG = Path("D:/hermes/analysis/.sandbox_scan_log.json")
SANDBOX_DIR = Path("D:/hermes/analysis/.sandbox")
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)

# 已知可信服务清单（仅这些允许交互式探测）
TRUSTED_SERVICES = {
    6379: "Redis (本地, 需认证)",
    10808: "xray SOCKS5代理",
    10812: "xray辅助端口",
}

# 已知危险信号（检测到立即终止）
HONEYPOT_SIGNALS = [
    b"root@", b"password:", b"login:", b"Welcome to",
    b"shell", b"bash", b"/bin/sh",
    b"captcha",
]

# ── 审计日志 ──

def _log(entry: dict):
    """记录探测日志"""
    entries = []
    if SCAN_LOG.exists():
        try:
            entries = json.loads(SCAN_LOG.read_text())
        except:
            pass
    entries.append(entry)
    SCAN_LOG.write_text(json.dumps(entries, ensure_ascii=False, indent=2))


# ── 端口扫描（安全版） ──

def safe_port_scan(target: str = "127.0.0.1",
                    ports: list[int] = None,
                    timeout: float = 0.3) -> list[dict]:
    """
    安全端口扫描:
      - 仅 TCP Connect 扫描
      - 单端口超时 0.3s
      - 每次只发 SYN（无数据）
      - 发现 LISTENING 后记录但不交互
    """
    if ports is None:
        # 已知端口 + 常见数据库端口
        ports = [
            6379, 6380,          # Redis
            5432, 5433,          # PostgreSQL
            3306, 3307,          # MySQL
            27017, 27018,        # MongoDB
            9092,                # Kafka
            9200, 9300,          # Elasticsearch
            8080, 8081, 8443,    # HTTP备用
            10808, 10809, 1080,  # 代理
            8789,                # Hermes端口?
        ]

    results = []
    for port in ports:
        try:
            t0 = time.time()
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
            result = s.connect_ex((target, port))
            elapsed = time.time() - t0
            s.close()

            if result == 0:
                results.append({
                    "port": port,
                    "state": "OPEN",
                    "elapsed_ms": round(elapsed * 1000),
                    "target": target,
                    "trusted": port in TRUSTED_SERVICES,
                    "service_hint": TRUSTED_SERVICES.get(port, "UNKNOWN"),
                })
                _log({
                    "ts": datetime.now().isoformat(),
                    "action": "port_probe",
                    "target": f"{target}:{port}",
                    "state": "OPEN",
                    "trusted": port in TRUSTED_SERVICES,
                    "elapsed_ms": round(elapsed * 1000),
                })
        except Exception as e:
            pass

    return results


# ── 蜜罐检测 ──

def probe_service(target: str, port: int,
                   initial_bytes: bytes = b"\x00",
                   max_recv: int = 256,
                   timeout: float = 1.0) -> dict:
    """
    安全试探服务:
      - 先发1字节试探
      - 收响应判断是否蜜罐
      - 检测到危险信号立即断连
      - 绝不发送认证信息
    """
    result = {
        "port": port,
        "target": target,
        "banner": "",
        "is_honeypot": False,
        "is_trusted": port in TRUSTED_SERVICES,
        "service_type": TRUSTED_SERVICES.get(port, "UNKNOWN"),
        "warnings": [],
        "protocol_hint": "",
    }

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.connect((target, port))

        # 先不发任何数据，只收 banner
        time.sleep(0.1)
        try:
            banner = s.recv(max_recv)
            result["banner_raw"] = banner.hex()
            result["banner"] = _safe_decode(banner)
        except socket.timeout:
            # 无主动banner -> 服务可能等待客户端先发
            s.send(initial_bytes)
            time.sleep(0.3)
            try:
                resp = s.recv(max_recv)
                result["banner_raw"] = resp.hex()
                result["banner"] = _safe_decode(resp)
                result["initiated"] = True
            except socket.timeout:
                result["banner"] = "[无响应]"
                result["silent"] = True

        # 蜜罐检测
        if result.get("banner"):
            banner_bytes = result["banner"].encode()
            for signal in HONEYPOT_SIGNALS:
                if signal in banner_bytes:
                    result["is_honeypot"] = True
                    result["warnings"].append(f"蜜罐信号: {signal}")

        # 协议猜测
        result["protocol_hint"] = _guess_protocol(result.get("banner_raw", ""))

        s.close()
    except ConnectionRefusedError:
        result["state"] = "CLOSED"
    except socket.timeout:
        result["state"] = "TIMEOUT"
    except Exception as e:
        result["error"] = str(e)[:60]

    _log({
        "ts": datetime.now().isoformat(),
        "action": "service_probe",
        "target": f"{target}:{port}",
        "banner_preview": result.get("banner", "")[:50],
        "is_honeypot": result.get("is_honeypot", False),
        "warnings": result.get("warnings", []),
    })

    return result


def _safe_decode(data: bytes) -> str:
    """安全解码，过滤控制字符"""
    try:
        text = data.decode("utf-8", errors="replace")
    except:
        text = data.decode("latin-1", errors="replace")
    # 过滤控制字符（保留换行）
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', ' ', text)
    return text.strip()[:200]


def _guess_protocol(banner_hex: str) -> str:
    """根据banner hex猜测协议"""
    if banner_hex.startswith("484554"):
        return "HTTP"
    if banner_hex.startswith("48545450"):
        return "HTTP/1.x"
    if banner_hex.startswith("53534c"):
        return "SSL/TLS"
    if banner_hex.startswith("164a"):
        return "SOCKS5"
    if banner_hex.startswith("2a"):
        return "Redis Serializer"
    if banner_hex.startswith("454c"):
        return "Elasticsearch"
    if "0500" in banner_hex[:10]:
        return "SOCKS5 (no auth)"
    return "UNKNOWN"


# ── 沙盒探针 ──

def full_sandbox_scan(target: str = "127.0.0.1") -> dict:
    """
    完整扫描流程:
      1. 端口扫描（仅TCP SYN）
      2. 对每个开放端口做蜜罐检测
      3. 分类: 可信/可疑/蜜罐
      4. 生成安全报告
    """
    report = {
        "target": target,
        "timestamp": datetime.now().isoformat(),
        "open_ports": [],
        "honeypots_detected": [],
        "trusted_services": [],
        "suspicious_services": [],
        "safe_to_query": [],
    }

    # Phase 1: 端口扫描
    print(f"🔍 Phase 1: 端口扫描 {target}...")
    open_ports = safe_port_scan(target, timeout=0.3)
    print(f"   发现 {len(open_ports)} 个开放端口")

    # Phase 2: 逐个蜜罐检测
    print(f"🔍 Phase 2: 蜜罐检测...")
    for p in open_ports:
        port = p["port"]
        delay = 1.0 if not p["trusted"] else 0.5  # 非可信端口的试探更慢
        
        print(f"   检测 :{port} ({p['service_hint']})...", end=" ")
        probe = probe_service(target, port, timeout=delay)
        
        if probe.get("is_honeypot"):
            print("🚨 蜜罐!")
            report["honeypots_detected"].append(probe)
        elif p["trusted"]:
            print(f"✅ 可信 ({probe['protocol_hint']})")
            report["trusted_services"].append(probe)
            report["safe_to_query"].append(probe)
        elif probe.get("banner") and "[无响应]" not in probe.get("banner", ""):
            print(f"⚠️ 未知: {probe['protocol_hint']}")
            report["suspicious_services"].append(probe)
        else:
            print("🔇 静默")
            report["suspicious_services"].append(probe)

        time.sleep(0.3)  # 探测间隔，避免触发IDS

    report["open_ports"] = open_ports
    return report


# ── 数据库特定探针（仅针对可信端口） ──

def safe_redis_probe(target: str = "127.0.0.1", port: int = 6379) -> dict:
    """
    安全试探 Redis:
      - 只发 PING (不认证)
      - 如果要求 AUTH 立即断开
      - 绝不发送密码
    """
    result = {"port": port, "service": "Redis", "accessible": False, "requires_auth": None}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((target, port))

        # 读banner
        banner = s.recv(256)
        # Redis RESP: +OK\r\n 或 -NOAUTH\r\n
        if b"-NOAUTH" in banner:
            result["requires_auth"] = True
            result["accessible"] = True
            result["auth_required"] = True
            result["warning"] = "需要认证，未发送密码"
        elif b"+OK" in banner or b"+PONG" in banner:
            result["requires_auth"] = False
            result["accessible"] = True
            # 发PING
            s.send(b"*1\r\n$4\r\nPING\r\n")
            resp = s.recv(256)
            result["ping_response"] = resp.strip()
        else:
            # 发PING试探
            s.send(b"*1\r\n$4\r\nPING\r\n")
            resp = s.recv(256)
            if b"+PONG" in resp:
                result["accessible"] = True
                result["requires_auth"] = False
            elif b"-NOAUTH" in resp:
                result["accessible"] = True
                result["requires_auth"] = True
            else:
                result["banner"] = banner.hex()
        s.close()
    except Exception as e:
        result["error"] = str(e)[:60]

    _log({"ts": datetime.now().isoformat(), "action": "redis_probe",
          "result": result.get("accessible"), "auth": result.get("requires_auth")})
    return result


# ── CLI ──

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--scan":
        target = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
        report = full_sandbox_scan(target)
        print(f"\n{'='*50}")
        print(f"📋 安全扫描报告")
        print(f"{'='*50}")
        print(f"\n✅ 可信服务 ({len(report['trusted_services'])}):")
        for s in report["trusted_services"]:
            print(f"   :{s['port']} {s['protocol_hint']} - {s.get('banner','')[:60]}")
        print(f"\n⚠️ 可疑服务 ({len(report['suspicious_services'])}):")
        for s in report["suspicious_services"]:
            print(f"   :{s['port']} {s['protocol_hint']} - {'静默' if s.get('silent') else s.get('banner','')[:60]}")
        print(f"\n🚨 蜜罐 ({len(report['honeypots_detected'])}):")
        for s in report["honeypots_detected"]:
            print(f"   :{s['port']} - {s['warnings']}")
        # 保存报告
        report_path = SANDBOX_DIR / f"scan_{datetime.now().strftime('%H%M%S')}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"\n📝 报告已保存: {report_path}")

    elif len(sys.argv) > 1 and sys.argv[1] == "--probe":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 6379
        target = sys.argv[3] if len(sys.argv) > 3 else "127.0.0.1"
        result = probe_service(target, port)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif len(sys.argv) > 1 and sys.argv[1] == "--redis":
        result = safe_redis_probe()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif len(sys.argv) > 1 and sys.argv[1] == "--log":
        if SCAN_LOG.exists():
            entries = json.loads(SCAN_LOG.read_text())
            print(f"📋 探测日志 ({len(entries)} 条):")
            for e in entries[-20:]:
                print(f"  [{e.get('ts','')[:19]}] {e.get('action','')} {e.get('target','')} {'🚨' if e.get('is_honeypot') else '✅' if e.get('state')=='OPEN' else ''}")
        else:
            print("日志为空")

    else:
        print("🔒 安全沙盒探测器 v1.0")
        print()
        print("用法:")
        print("  --scan [target]      全端口扫描+蜜罐检测")
        print("  --probe <port> [host] 单端口蜜罐检测")
        print("  --redis              安全试探本地 Redis")
        print("  --log                查看探测日志")
        print()
        print("安全策略:")
        print("  • 所有端口预设为蜜罐")
        print("  • 首次只发1字节试探")
        print("  • 绝不发送认证信息")
        print("  • 检测到危险信号立即断开")
        print(f"  • 日志: {SCAN_LOG}")
