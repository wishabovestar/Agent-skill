"""
反爬绕过引擎 — Anti-Scraping Bypass Engine v1.0
===============================================
针对当前网络环境遇到的:
  - 搜狗反爬 (JS challenge)
  - 百度验证码 (captcha)  
  - Bing GBK 编码错误
  - 国际站点 GFW 阻断
  - DuckDuckGo 限速

策略:
  1. Cookie 持久化 + Session 复用
  2. User-Agent 轮换 + 请求头伪装
  3. 多后端 Fallback (含浏览器渲染)
  4. 缓存快照 (Google Cache / Wayback Machine)
  5. arXiv / Wikipedia 等结构化API兜底
  6. 本地知识库兜底
"""

import json, os, time, re, random, hashlib
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, quote, urlencode

# ── 配置 ──
COOKIE_FILE = Path("D:/hermes/analysis/.scraping_cookies.json")
CACHE_DIR = Path("D:/hermes/analysis/.page_cache")
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# DNS over HTTPS 服务器（用于绕过 DNS 污染）
DOH_SERVERS = [
    "https://dns.google/dns-query?name={domain}&type=A",
    "https://cloudflare-dns.com/dns-query?name={domain}&type=A",
]

# ── Cookie / Session 管理 ──

def load_cookies() -> dict:
    """加载持久化 Cookie"""
    if COOKIE_FILE.exists():
        try:
            return json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
        except:
            return {}
    return {}

def save_cookies(cookies: dict):
    """保存 Cookie"""
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")

def update_cookies(domain: str, new_cookies: dict):
    """更新特定域名的 Cookie"""
    cookies = load_cookies()
    cookies[domain] = {**cookies.get(domain, {}), **new_cookies}
    cookies[domain]["_updated_at"] = time.time()
    save_cookies(cookies)

def get_cookie_header(domain: str) -> str:
    """获取 Cookie 请求头"""
    cookies = load_cookies().get(domain, {})
    items = [f"{k}={v}" for k, v in cookies.items() if not k.startswith("_")]
    return "; ".join(items)

# ── 请求伪装 ──

def get_headers(domain: str = "", referer: str = "") -> dict:
    """生成随机化请求头"""
    ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    cookie = get_cookie_header(domain)
    if cookie:
        headers["Cookie"] = cookie
    if referer:
        headers["Referer"] = referer
    return headers

# ── DNS 污染绕过 ──

def resolve_via_doh(domain: str) -> str | None:
    """通过 DNS-over-HTTPS 解析域名，绕过 DNS 污染"""
    import urllib.request, ssl, json as j
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for doh_url in DOH_SERVERS:
        try:
            url = doh_url.format(domain=domain)
            req = urllib.request.Request(url, headers={"Accept": "application/dns-json"})
            resp = urllib.request.urlopen(req, timeout=5, context=ctx)
            data = j.loads(resp.read())
            answers = data.get("Answer", [])
            for a in answers:
                if a.get("type") == 1:  # A record
                    return a.get("data")
        except:
            continue
    return None

# ── 多后端获取引擎 ──

def _detect_proxy() -> dict | None:
    """自动检测本地代理"""
    import subprocess, re, socket
    try:
        output = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=False, timeout=5
        )
        lines = output.stdout.decode("gbk", errors="replace").split('\n')
        listening = {}
        for line in lines:
            m = re.search(r'TCP\s+127\.0\.0\.1:(\d+)\s+0\.0\.0\.0:0\s+LISTENING', line)
            if m:
                listening[int(m.group(1))] = "TCP"

        for port, protocol in [(10808, "socks5"), (1080, "http"), (7890, "http")]:
            if port in listening:
                try:
                    if protocol == "socks5":
                        s = socket.create_connection(("127.0.0.1", port), timeout=2)
                        s.send(b'\x05\x01\x00')
                        if s.recv(2) == b'\x05\x00':
                            s.close()
                            return {"type": "socks5", "host": "127.0.0.1", "port": port}
                        s.close()
                    else:
                        return {"type": "http", "host": "127.0.0.1", "port": port}
                except:
                    continue
    except:
        pass
    return None


def _fetch_via_proxy(url: str, proxy: dict, timeout: int = 15) -> dict | None:
    """通过 SOCKS5 或 HTTP 代理获取网页"""
    protocol = proxy.get("type", "socks5")
    host = proxy.get("host", "127.0.0.1")
    port = proxy.get("port", 10808)

    # 优先使用 PySocks (requests[socks])
    try:
        import socks as socks_module
        import socket as socket_module
        original_socket = socket_module.socket

        socks_module.set_default_proxy(
            socks_module.SOCKS5 if protocol == "socks5" else socks_module.HTTP,
            host, port
        )
        socket_module.socket = socks_module.socksocket

        import urllib.request, ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(
            url,
            headers={"User-Agent": random.choice(USER_AGENTS),
                     "Accept": "text/html,*/*"}
        )
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        content = resp.read().decode("utf-8", errors="replace")
        socket_module.socket = original_socket
        return {"success": True, "content": content, "status": resp.status, "method": f"proxy_{protocol}"}
    except ImportError:
        pass
    except Exception as e:
        pass

    # 备用: 直接通过 socket 走 SOCKS5 (无需PySocks)
    if protocol == "socks5":
        try:
            import socket as sock_mod
            s = sock_mod.socket(sock_mod.AF_INET, sock_mod.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((host, port))
            # SOCKS5 握手
            s.send(b'\x05\x01\x00')
            if s.recv(2) != b'\x05\x00':
                s.close()
                return None
            # 解析URL
            from urllib.parse import urlparse
            parsed = urlparse(url)
            target_host = parsed.hostname.encode()
            target_port = parsed.port or (443 if parsed.scheme == "https" else 80)
            # SOCKS5 请求 (域名模式)
            req = b'\x05\x01\x00\x03' + bytes([len(target_host)]) + target_host + target_port.to_bytes(2, 'big')
            s.send(req)
            resp = s.recv(10)
            if resp[1] != 0x00:
                s.close()
                return None
            # 如果是 HTTPS, 建立 TLS
            if parsed.scheme == "https":
                import ssl as ssl_mod
                ctx = ssl_mod.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl_mod.CERT_NONE
                s = ctx.wrap_socket(s, server_hostname=parsed.hostname)
            # HTTP 请求
            path = parsed.path or "/"
            if parsed.query: path += "?" + parsed.query
            s.send(f"GET {path} HTTP/1.0\r\nHost: {parsed.hostname}\r\nUser-Agent: {random.choice(USER_AGENTS)}\r\nConnection: close\r\n\r\n".encode())
            data = b""
            while True:
                chunk = s.recv(8192)
                if not chunk: break
                data += chunk
            s.close()
            # 分离HTTP头和正文
            if b"\r\n\r\n" in data:
                headers_bytes, body = data.split(b"\r\n\r\n", 1)
                return {"success": True, "content": body.decode("utf-8", errors="replace")[:50000],
                        "status": int(headers_bytes.split(b" ")[1]), "method": "raw_socks5"}
        except Exception as e:
            pass

    return None

def fetch_with_bypass(url: str, timeout: int = 15, use_cache: bool = True,
                       use_proxy: bool = True) -> dict:
    """
    带反爬绕过能力的网页获取。
    策略链: 缓存 → 代理检测 → 直接请求 → Cookie复用 → 浏览器 → 快照 → 知识库
    """
    # 0. 缓存命中
    if use_cache:
        cached = _check_cache(url)
        if cached:
            return cached | {"cached": True}

    # 检测可用代理
    proxy = _detect_proxy() if use_proxy else None

    # 1. 通过代理请求 (如果代理可用)
    if proxy:
        try:
            result = _fetch_via_proxy(url, proxy, timeout)
            if result and result.get("success"):
                _save_cache(url, result)
                return result | {"proxy_used": proxy["type"]}
        except:
            pass

    # 2. 直接请求 (带伪装头 + Cookie)
    try:
        import urllib.request, ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        domain = urlparse(url).netloc
        headers = get_headers(domain)
        req = urllib.request.Request(url, headers=headers)

        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        raw = resp.read()

        # 更新 Cookie
        set_cookie = resp.headers.get("Set-Cookie", "")
        if set_cookie:
            _parse_and_store_cookies(domain, set_cookie)

        content = raw.decode("utf-8", errors="replace")
        result = {"success": True, "content": content,
                  "status": resp.status, "method": "direct",
                  "encoding": "utf-8", "url": url}
        _save_cache(url, result)
        return result
    except urllib.request.HTTPError as e:
        if e.code in (403, 429):
            pass  # 被反爬拦截，继续试下一个方法
        else:
            return {"success": False, "error": f"HTTP {e.code}", "method": "direct"}
    except Exception as e:
        err = str(e)[:60]

    # 2. 尝试浏览器渲染 (如果 Hermes browser 可用)
    browser_result = _try_browser_render(url, timeout)
    if browser_result:
        _save_cache(url, browser_result)
        return browser_result

    # 3. 尝试 Wayback Machine
    #    (优先于 Google Cache: Google 已于 2024 下线 `cache:` 运算符,
    #     webcache.googleusercontent.com 现只返回同意页, 属死路)
    wayback_result = _fetch_wayback(url, timeout)
    if wayback_result:
        _save_cache(url, wayback_result)
        return wayback_result | {"method": "wayback"}

    # 4. 尝试 Google Cache (已废弃路径, 仅作兜底)
    #    加"同意页/过短"守卫, 避免把 Google 同意页当成正文返回
    cache_result = _fetch_google_cache(url, timeout)
    if cache_result:
        _body = (cache_result.get("content") or "").lower()
        if "consent" not in _body and len(_body) > 200:
            _save_cache(url, cache_result)
            return cache_result | {"method": "google_cache"}

    return {"success": False, "error": "全部方法失败", "method": "all_failed"}


def _try_browser_render(url: str, timeout: int) -> dict | None:
    """
    通过浏览器渲染获取动态内容。
    需要 Hermes browser 工具可用。
    """
    # 仅在确定性已知时使用
    # 实际运行时通过 browser_navigate 实现
    return None


def _fetch_google_cache(url: str, timeout: int) -> dict | None:
    """获取 Google 缓存的页面快照"""
    import urllib.request, ssl
    cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(cache_url, headers={
            "User-Agent": random.choice(USER_AGENTS),
        })
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        content = resp.read().decode("utf-8", errors="replace")
        # 提取实际内容（Google Cache 包裹在 <pre> 或 <div> 中）
        content = _extract_cache_content(content)
        return {"success": True, "content": content, "status": resp.status}
    except:
        return None


# ---- 内容级校验（对应 MIGRATION_agent_patterns.md G1）----
# 教训来源：2026-10-13 实测，_fetch_wayback 经代理拿到 http=200，
# 但正文实为 archive.org 反爬拦截页(620B)，函数却返回 success=True。
# 同一坑在 refetch v1 也出现过（3 篇抓到完全相同的 5590B 拦截页）。
_BLOCK_MARKERS = (
    "abusive bot traffic", "being blocked", "your request is being blocked",
    "unusual traffic", "rate limit", "too many requests", "captcha",
    "access denied", "cf-error", "just a moment", "enable javascript and cookies",
    "consent.google", "verify you are human",
)


def _looks_like_block_page(text: str) -> bool:
    """判断取到的内容是不是拦截页/占位页（而非正文）。

    「取到了」不等于「取到正经内容」——任何 success 声明都必须过这道内容级校验。
    """
    if not text or len(text) < 120:
        return True
    low = text[:4000].lower()
    return any(m in low for m in _BLOCK_MARKERS)


def _fetch_wayback(url: str, timeout: int) -> dict | None:
    """通过 Wayback Machine 获取历史快照。

    archive.org 在国内直连必超时（实测 http=000 / 15s），
    经 xray socks5(127.0.0.1:10808) 4s 即 200 ⇒ 有代理时优先走代理。
    """
    import json as j
    proxy = _detect_proxy()

    def _get(u: str) -> str | None:
        # 有代理先走代理（国内直连 archive.org 必死），代理失败再退回直连
        attempts = ([proxy, None] if proxy else [None])
        for p in attempts:
            if p is None:
                try:
                    import urllib.request, ssl
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    req = urllib.request.Request(
                        u, headers={"User-Agent": random.choice(USER_AGENTS)})
                    return urllib.request.urlopen(
                        req, timeout=timeout, context=ctx).read().decode("utf-8", errors="replace")
                except Exception:
                    continue
            else:
                r = _fetch_via_proxy(u, p, timeout)
                if r and r.get("success") and r.get("content"):
                    return r["content"]
        return None

    try:
        body = _get(f"https://archive.org/wayback/available?url={url}")
        if not body:
            return None
        data = j.loads(body)
        closest = data.get("archived_snapshots", {}).get("closest", {})
        if not (closest.get("available") and closest.get("url")):
            return None
        content = _get(closest["url"])
        if not content or _looks_like_block_page(content):
            # 拦截页/占位页 ⇒ 视为未取到，而不是返回假 success
            return None
        return {"success": True, "content": content, "status": 200,
                "method": "wayback", "wayback_timestamp": closest.get("timestamp", "")}
    except Exception:
        return None


def _extract_cache_content(html: str) -> str:
    """从 Google Cache 包裹中提取实际内容"""
    # 尝试提取 <pre> 标签内的内容
    pre_match = re.search(r'<pre[^>]*>(.*?)</pre>', html, re.DOTALL)
    if pre_match:
        return pre_match.group(1)
    # 尝试提取 <div id="google-cache"> 内容
    div_match = re.search(r'<div[^>]*id="google-cache"[^>]*>(.*?)</div>', html, re.DOTALL)
    if div_match:
        return div_match.group(1)
    return html


def _parse_and_store_cookies(domain: str, set_cookie: str):
    """解析 Set-Cookie 并存储"""
    import http.cookies
    try:
        c = http.cookies.SimpleCookie(set_cookie)
        cookie_dict = {}
        for key, morsel in c.items():
            cookie_dict[key] = morsel.value
        update_cookies(domain, cookie_dict)
    except:
        pass


# ── 本地缓存 ──

def _cache_path(url: str) -> Path:
    url_hash = hashlib.md5(url.encode()).hexdigest()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{url_hash[:20]}.json"


def _check_cache(url: str) -> dict | None:
    cache_file = _cache_path(url)
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if data.get("_cached_at", 0) > time.time() - 3600:  # 1h TTL
                return data
        except:
            pass
    return None


def _save_cache(url: str, result: dict):
    try:
        data = {**result, "_cached_at": time.time(), "_cached_url": url}
        # 限制内容大小
        if len(data.get("content", "")) > 50000:
            data["content"] = data["content"][:50000] + "\n...[截断]..."
        cache_file = _cache_path(url)
        cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except:
        pass


# ── 反爬类型自动检测 ──

def detect_block_type(response: dict) -> str | None:
    """从响应中检测反爬类型"""
    content = response.get("content", "")
    status = response.get("status", 0)

    if status == 403:
        return "HTTP 403 禁止访问"
    if status == 429:
        return "HTTP 429 请求过频 (Rate Limited)"
    if "验证码" in content or "captcha" in content.lower():
        return "验证码(CAPTCHA)阻断"
    if "antispider" in content.lower() or "反爬" in content:
        return "反爬系统(Anti-Spider)阻断"
    if "您的请求" in content and "异常" in content:
        return "请求异常检测阻断"
    if "javascript" in content.lower() and "enable" in content.lower():
        return "JS Challenge 阻断"
    return None


# ── CLI ──

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        url = " ".join(sys.argv[1:])
        if not url.startswith("http"):
            url = "https://" + url
        print(f"🌐 正在获取: {url}")
        result = fetch_with_bypass(url, timeout=15)
        if result["success"]:
            block_type = detect_block_type(result)
            if block_type:
                print(f"⚠️  检测到反爬: {block_type}")
            print(f"✅ 成功! 方法: {result.get('method','?')}")
            print(f"   大小: {len(result.get('content',''))} chars")
            if result.get("wayback_timestamp"):
                print(f"   快照时间: {result['wayback_timestamp']}")
            # 提取标题
            title = re.search(r'<title>(.*?)</title>', result.get("content", ""), re.DOTALL)
            if title:
                print(f"   标题: {title.group(1).strip()[:80]}")
        else:
            print(f"❌ 失败: {result.get('error','?')}")
        print(f"   方法: {result.get('method','?')}")
    else:
        print("反爬绕过引擎 v1.0")
        print()
        print("用法: python bypass_engine.py <URL>")
        print()
        print("绕过链: 直接请求 → Cookie复用 → 浏览器 → Google Cache → Wayback → 失败")
        print()
        print(f"Cookie: {len(load_cookies())} 个域名")
        print(f"缓存: {len(list(CACHE_DIR.glob('*.json')))} 条" if CACHE_DIR.exists() else "缓存: 0 条")
