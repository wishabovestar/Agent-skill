"""
GFW/反爬绕过研究报告 — 巡天融合版 v1.0
========================================
巡天(searcher) Agent 专用: 网络信息检索与GFW绕过策略

基于2026-07-10全网段实测数据:
  - DuckDuckGo: 持续超时 (Rate Limit)
  - Google: GFW完全阻断
  - Bing国际版: GFW阻断
  - Bing CN: 内容过滤 (不显示敏感新闻)
  - 百度: CAPTCHA验证码
  - 搜狗: JS Challenge (反爬)
  - Reuters/Guardian: GFW阻断
  - Wikipedia: GFW阻断
"""

import json, time, socket, ssl, subprocess, re, random
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, quote

REPORT_FILE = Path("D:/hermes/analysis/.gfw_research_report.json")

# ═══════════════════════════════════════════════════
# 1. GFW 阻断技术分类
# ═══════════════════════════════════════════════════

GFW_TECHNIQUES = {
    "DNS_POLLUTION": {
        "name": "DNS污染",
        "symptom": "域名解析返回虚假IP或超时",
        "detection": "nslookup 返回非预期IP / 超时",
        "bypass": [
            "DNS-over-HTTPS (DoH): dns.google, cloudflare-dns.com",
            "DNS-over-TLS (DoT): 1.1.1.1, 8.8.8.8",
            "Hosts文件直接指定IP",
            "代理DNS解析 (SOCKS5远程解析)",
        ],
        "tools": ["dnspython", "cloudflare-dns", "dnscrypt"],
    },
    "IP_BLOCKING": {
        "name": "IP封锁",
        "symptom": "TCP连接超时(RST)或黑洞路由",
        "detection": "ping超时 / traceroute中途断连",
        "bypass": [
            "CDN前置 (cloudflare/cloudfront)",
            "反向代理服务器中转",
            "Tor网络 (.onion)",
            "SSH隧道/端口转发",
        ],
        "tools": ["cloudflared", "frp", "shadowsocks", "v2ray"],
    },
    "SNI_FILTERING": {
        "name": "SNI过滤 (TLS指纹)",
        "symptom": "TLS握手被中断 (TLS handshake failure)",
        "detection": "openssl s_client连接失败",
        "bypass": [
            "TLS伪装 (ESNI/ECH)",
            "CDN域名前置 (domain fronting)",
            "WebSocket over TLS",
        ],
        "tools": ["trojan", "v2ray+tls", "naiveproxy"],
    },
    "DEEP_PACKET_INSPECTION": {
        "name": "深度包检测 (DPI)",
        "symptom": "HTTP/HTTPS关键词匹配后阻断",
        "detection": "特定关键词HTTP请求被RST",
        "bypass": [
            "TLS指纹伪装 (JA3/JA3S)",
            "协议混淆 (obfuscation)",
            "随机填充 (padding)",
        ],
        "tools": ["v2ray+mkcp", "trojan-go", "obfs4"],
    },
    "RATE_LIMITING": {
        "name": "请求频率限制",
        "symptom": "同一IP短时内多次请求被封",
        "detection": "HTTP 429 / 连接被重置",
        "bypass": [
            "IP轮换 (代理池)",
            "请求间隔随机化 (1-5s正态分布)",
            "缓存层减少重复请求",
        ],
        "tools": ["已实现: human_crawler.py"],
    },
    "CAPTCHA": {
        "name": "验证码",
        "symptom": "图形验证码/JS Challenge",
        "detection": "返回页含captcha/antispider/验证",
        "bypass": [
            "Google Cache快照",
            "Wayback Machine历史存档",
            "浏览器渲染+Stealth (Browserbase)",
        ],
        "tools": ["已实现: bypass_engine.py"],
    },
    "CONTENT_FILTER": {
        "name": "内容过滤",
        "symptom": "搜索结果被过滤 (如Bing CN不显示敏感新闻)",
        "detection": "搜索特定关键词获得0结果",
        "bypass": [
            "使用境外搜索引擎 (Bing国际/Google)",
            "走代理访问原站",
            "RSS/API绕过Web界面",
        ],
        "tools": ["xray SOCKS5", "Tor"],
    },
}


# ═══════════════════════════════════════════════════
# 2. 多层绕过策略 (巡天专用)
# ═══════════════════════════════════════════════════

BYPASS_STRATEGIES = {
    "search": {
        "description": "搜索引擎检索",
        "chain": [
            {"name": "web_search(ddgs)", "success_rate": "0% (超时)", "action": "尝试→超时→下一步"},
            {"name": "curl直调Bing CN", "success_rate": "50% (但内容过滤)", "action": "可用→注意过滤"},
            {"name": "arXiv API", "success_rate": "90% 学术", "action": "✅ 推荐学术搜索"},
            {"name": "GitHub API", "success_rate": "70% 代码搜索", "action": "✅ 推荐代码/项目"},
            {"name": "Google Cache", "success_rate": "30% 不稳定", "action": "尝试→失败→下一步"},
            {"name": "Wayback Machine", "success_rate": "40% 不稳定", "action": "尝试→失败→下一步"},
        ],
    },
    "website": {
        "description": "特定网站内容获取",
        "chain": [
            {"name": "代理SOCKS5", "success_rate": "依赖远程", "action": "xray:10808 → 远程不可达"},
            {"name": "Tor SOCKS5", "success_rate": "待安装", "action": "setup_tor.py → winget install Tor"},
            {"name": "直接请求+伪装", "success_rate": "30% 国内站", "action": "UA轮换+Cookie→可用"},
            {"name": "Browser渲染", "success_rate": "40% JS站", "action": "browser_navigate → 编码问题"},
        ],
    },
    "academic": {
        "description": "学术/技术内容",
        "chain": [
            {"name": "arXiv API", "success_rate": "90%", "action": "✅ 最佳学术来源"},
            {"name": "Semantic Scholar", "success_rate": "70%", "action": "需要代理"},
            {"name": "本地知识库", "success_rate": "100% 离线", "action": "✅ 已缓存内容直接可用"},
        ],
    },
}


# ═══════════════════════════════════════════════════
# 3. 实际连通性测试函数 (巡天调用)
# ═══════════════════════════════════════════════════

def test_connectivity(targets: list[str] = None) -> list[dict]:
    """测试各后端的连通性 (巡天专用)"""
    if not targets:
        targets = [
            "https://www.google.com",
            "https://cn.bing.com",
            "http://export.arxiv.org",
            "https://api.github.com",
            "https://webcache.googleusercontent.com",
            "https://archive.org",
        ]
    results = []
    for url in targets:
        t0 = time.time()
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=8, context=ctx)
            elapsed = time.time() - t0
            results.append({
                "url": url[:50],
                "status": resp.status,
                "elapsed": round(elapsed, 1),
                "reachable": True,
            })
        except Exception as e:
            elapsed = time.time() - t0
            results.append({
                "url": url[:50],
                "status": str(e)[:30],
                "elapsed": round(elapsed, 1),
                "reachable": False,
            })
        time.sleep(1)  # 礼貌间隔
    return results


def scan_proxy_ports() -> list[dict]:
    """扫描本地代理端口"""
    proxy_ports = [10808, 1080, 7890, 9050, 10809, 1081]
    results = []
    for port in proxy_ports:
        try:
            s = socket.socket()
            s.settimeout(1)
            s.connect(("127.0.0.1", port))
            s.close()
            results.append({"port": port, "status": "open"})
        except:
            results.append({"port": port, "status": "closed"})
    return results


def generate_report() -> dict:
    """生成完整绕道研究报告"""
    return {
        "timestamp": datetime.now().isoformat(),
        "gfw_techniques": {k: {"name": v["name"], "bypass_count": len(v["bypass"])}
                           for k, v in GFW_TECHNIQUES.items()},
        "bypass_strategies": {k: {"chain_length": len(v["chain"])}
                              for k, v in BYPASS_STRATEGIES.items()},
        "connectivity": test_connectivity(),
        "proxy_ports": scan_proxy_ports(),
        "recommendation": (
            "当前最优搜索路径:\n"
            "  1. 本地知识库 (knowledge_store) → 100% 离线可用\n"
            "  2. arXiv API → 90% 学术搜索\n"
            "  3. GitHub API → 70% 代码搜索\n"
            "  4. Bing CN (curl直调) → 50% 但有内容过滤\n"
            "  5. Google Cache / Wayback → 30-40% 不稳定\n"
            "待 xray 远程恢复后: Google/Wikipedia/Reuters 全可达"
        ),
    }


if __name__ == "__main__":
    report = generate_report()
    # 保存
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    import json
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"GFW研究报告已保存: {REPORT_FILE}")
    print(f"\n推荐策略:\n{report['recommendation']}")
