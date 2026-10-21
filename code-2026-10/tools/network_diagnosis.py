"""
Hermes 网络访问瓶颈诊断与改善计划 v1.0
========================================
基于2026-07-10实测：DuckDuckGo超时、Bing编码错误、百度验证码、搜狗反爬、
Google不可达、国际站点(Rueters/Guardian)连接拒绝

核心发现: 当前后端100%依赖 ddgs(DuckDuckGo)，缺少任何 fallback 链
"""

import json, os, platform, subprocess, urllib.request, ssl, time
from datetime import datetime

REPORT_FILE = "D:/hermes/analysis/network_diagnosis.md"

def check_backend(name: str, url: str, timeout: int = 8) -> dict:
    """检查单个后端的可达性"""
    result = {"backend": name, "url": url, "reachable": False, "status": "", "latency_ms": 0}
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        start = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        result["latency_ms"] = int((time.time() - start) * 1000)
        result["reachable"] = True
        result["status"] = f"{resp.status} ({len(resp.read())} bytes)"
    except Exception as e:
        result["status"] = str(e)[:80]
    return result

def run():
    backends = [
        ("DuckDuckGo(搜索)", "https://duckduckgo.com/html/?q=test"),
        ("Bing(国际版)", "https://www.bing.com/search?q=test&setlang=en-US"),
        ("Bing(中文版)", "https://cn.bing.com/search?q=test&setlang=zh-Hans"),
        ("百度", "http://www.baidu.com/s?wd=test&ie=utf-8"),
        ("搜狗", "https://www.sogou.com/web?query=test"),
        ("Google", "https://www.google.com/search?q=test"),
        ("Reuters", "https://www.reuters.com"),
        ("GitHub API", "https://api.github.com"),
        ("arXiv API", "http://export.arxiv.org/api/query?search_query=all:test"),
        ("腾讯新闻", "https://news.qq.com"),
    ]

    print(f"🌐 Hermes 网络诊断报告 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")
    print(f"{'后端':<20} {'状态':<30} {'延迟':<8}")
    print(f"{'─'*60}")

    results = []
    for name, url in backends:
        r = check_backend(name, url)
        r["name"] = name
        results.append(r)
        status_icon = "✅" if r["reachable"] else "❌"
        latency = f"{r['latency_ms']}ms" if r["reachable"] else "—"
        print(f"{status_icon} {name:<18} {r['status'][:28]:<28} {latency:<8}")

    print()
    reachable = sum(1 for r in results if r["reachable"])
    print(f"📊 总后端: {len(results)}, 可达: {reachable}, 不可达: {len(results)-reachable}")

    # 生成改善建议
    print()
    print("🔧 建议的 fallback 链配置:")
    chain = [
        r["name"] for r in sorted(results, key=lambda x: not x["reachable"])
        if "搜索" in r["name"] or "api" in r["backend"].lower()
    ]
    for i, c in enumerate(chain):
        status = "✅" if any(r["reachable"] and r["name"] == c for r in results) else "❌"
        print(f"  {i+1}. {status} {c}")

    # 保存报告
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    report = f"""# 🌐 Hermes 网络诊断报告

**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**平台**: {platform.system()} {platform.release()}
**Python**: {platform.python_version()}

## 后端可达性

| 后端 | 状态 | 延迟 | 问题 |
|:-----|:----:|:----:|:-----|
"""
    for r in results:
        icon = "✅" if r["reachable"] else "❌"
        lat = f"{r['latency_ms']}ms" if r["reachable"] else "—"
        report += f"| {r['name']} | {icon} | {lat} | {r['status']} |\n"

    report += """
## 当前配置问题

1. **`web.search_backend` = ddgs** (默认) — DuckDuckGo 在国内环境经常超时、限速
2. **`web.extract_backend` = 未配置** — ddgs 不支持 URL 内容提取，`web_extract` 总是失败
3. **无 fallback 链** — 搜索失败后不会自动切换到其他后端
4. **无缓存层** — 相同查询每次重复请求，浪费 Token 和带宽
5. **无代理/VPN** — GFW 导致 Google/Reuters/GitHub 国际站点不可达

## 改善方案
"""
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n📝 报告已保存: {REPORT_FILE}")

if __name__ == "__main__":
    run()
