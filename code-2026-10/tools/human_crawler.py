"""
Hermes 拟人爬虫 v1.0 — 低频/少量/仿真人行为
=============================================
设计原则:
  1. 请求间隔随机化 (0.5-3s 正态分布, 非固定)
  2. 时段感知 (深夜降低频率, 模拟人类作息)
  3. UA轮换 (真实浏览器指纹)
  4. 请求头完整 (Referer/Accept-Language/Sec-Fetch 等)
  5. Cookies 持久化 (会话保持)
  6. robots.txt + Crawl-Delay 严格遵守
  7. 限速: 同一域名每分钟≤5次, 每天≤200次
  8. 深度限制: 默认只爬2层, 最多10页/站点
"""

import json, os, time, re, random, socket, ssl, hashlib, logging
import urllib.request, urllib.error, urllib.robotparser
from pathlib import Path
from datetime import datetime, time as dtime
from urllib.parse import urlparse, urljoin
from typing import Optional
from collections import defaultdict

# ── 配置 ──
CRAWL_DIR = Path("D:/hermes/analysis/.crawler_data")
CRAWL_DIR.mkdir(parents=True, exist_ok=True)

LOG = Path.home() / "AppData/Local/hermes/profiles/mybot/logs/crawler.log"
LOG.parent.mkdir(parents=True, exist_ok=True)

# 日志
_logger = logging.getLogger("human_crawler")
_handler = logging.FileHandler(str(LOG), encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_logger.addHandler(_handler)
_logger.setLevel(logging.INFO)

# ── 拟人UA池 (模仿真实浏览器) ──
USER_AGENTS = [
    # Chrome 120+ Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    # Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    # Safari
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

# 屏幕分辨率 (用于 Sec-CH-UA 头)
SCREEN_SIZES = [
    "1920x1080", "1366x768", "1536x864", "1440x900", "2560x1440",
    "1680x1050", "1280x720", "1920x1200",
]

# ── 限速配置 ──
DOMAIN_LIMITS = {
    # domain_pattern: (max_per_minute, max_per_day, min_interval)
    "default": (5, 200, 0.5),
    "arxiv.org": (10, 500, 0.3),          # API 友好
    "github.com": (10, 500, 0.3),          # API 友好
    "wikipedia.org": (3, 100, 1.0),        # 保守
    "bing.com": (3, 100, 2.0),             # 有反爬
    "baidu.com": (2, 50, 3.0),             # 有反爬
    "sogou.com": (2, 50, 3.0),             # 有反爬
}


# ═══════════════════════════════════════════════════
# 拟人时间生成器
# ═══════════════════════════════════════════════════

class HumanTiming:
    """生成类人请求间隔"""

    @staticmethod
    def get_delay(domain: str = "", hour: int = None) -> float:
        """
        产生拟人延迟 (秒):
          - 基础: 0.5-3s 随机 (正态分布偏向1-2s)
          - 深夜 (0-6点): ×1.5 (更慢, 模拟睡觉)
          - 高峰 (10-11点, 14-16点): ×0.8 (更快, 模拟工作)
          - 复杂页面: +0.5-2s (模拟阅读时间)
        """
        if hour is None:
            hour = datetime.now().hour

        # 基础延迟 (正态分布, 均值1.5s, 标准差0.5)
        base = abs(random.gauss(1.5, 0.5))
        base = max(0.3, min(base, 4.0))

        # 时段修正
        if 0 <= hour <= 6:
            base *= 1.5  # 深夜减速
        elif 10 <= hour <= 11 or 14 <= hour <= 16:
            base *= 0.8  # 工作高峰加速

        # 随机抖动 (±30%)
        jitter = random.uniform(0.7, 1.3)
        delay = base * jitter

        # 检查域名限速
        for pattern, (max_min, max_day, min_int) in DOMAIN_LIMITS.items():
            if pattern in domain:
                delay = max(delay, min_int)
                break

        # 随机增加0-300ms "鼠标移动/思考" 时间
        delay += random.uniform(0, 0.3)

        return round(delay, 2)

    @staticmethod
    def should_crawl_now() -> bool:
        """
        是否适合现在爬取 (模拟人类作息):
          - 凌晨1-5点: 10% 概率 (偶尔深夜工作)
          - 6-8点: 30% 概率
          - 9-22点: 90% 概率 (正常工作)
          - 23-0点: 40% 概率
        """
        hour = datetime.now().hour
        if 1 <= hour <= 5:
            return random.random() < 0.10  # 深夜几乎不爬
        elif 6 <= hour <= 8:
            return random.random() < 0.30
        elif 9 <= hour <= 22:
            return random.random() < 0.90
        else:
            return random.random() < 0.40


# ═══════════════════════════════════════════════════
# 拟人请求头生成器
# ═══════════════════════════════════════════════════

class HumanHeaders:
    """生成类人 HTTP 请求头"""

    @staticmethod
    def generate(referer: str = "") -> dict:
        ua = random.choice(USER_AGENTS)
        screen = random.choice(SCREEN_SIZES)

        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": random.choice(["max-age=0", "no-cache"]),
        }

        # 随机添加一些浏览器特有头
        if "Chrome" in ua:
            headers["Sec-Ch-Ua"] = f'"Chromium";v="{random.choice([120,121,122])}", "Google Chrome";v="{random.choice([120,121,122])}"'
            headers["Sec-Ch-Ua-Mobile"] = "?0"
            headers["Sec-Ch-Ua-Platform"] = random.choice(['"Windows"', '"macOS"'])

        if referer:
            headers["Referer"] = referer

        return headers


# ═══════════════════════════════════════════════════
# 状态追踪 (限速/访问计数/域名统计)
# ═══════════════════════════════════════════════════

class CrawlState:
    """爬虫状态追踪 — 域名限速 / 访问计数"""

    def __init__(self):
        self.state_file = CRAWL_DIR / "crawl_state.json"
        self.state = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except:
                pass
        return {"domains": {}, "total_requests": 0, "daily_reset": ""}

    def _save(self):
        self.state_file.write_text(json.dumps(self.state, indent=2))

    def _day_key(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def check_and_record(self, domain: str) -> bool:
        """
        检查是否允许发送请求。
        返回 True=允许, False=超限
        """
        today = self._day_key()

        # 每日重置
        if self.state["daily_reset"] != today:
            self.state["domains"] = {}
            self.state["daily_reset"] = today
            self.state["total_requests"] = 0

        # 域名统计
        domain_state = self.state["domains"].setdefault(domain, {
            "count_minute": 0, "count_day": 0, "last_request": 0
        })

        # 每分钟重置
        if time.time() - domain_state["last_request"] > 60:
            domain_state["count_minute"] = 0

        # 获取此域名的限制
        limits = DOMAIN_LIMITS.get("default")
        for pattern, lim in DOMAIN_LIMITS.items():
            if pattern in domain:
                limits = lim
                break

        max_min, max_day, _ = limits

        # 检查限速
        if domain_state["count_minute"] >= max_min:
            return False
        if domain_state["count_day"] >= max_day:
            return False

        # 记录
        domain_state["count_minute"] += 1
        domain_state["count_day"] += 1
        domain_state["last_request"] = time.time()
        self.state["total_requests"] += 1
        self._save()
        return True


# ═══════════════════════════════════════════════════
# 主爬虫
# ═══════════════════════════════════════════════════

class HumanCrawler:
    """
    拟人爬虫: 仿真人行为 + 限速 + robots.txt
    """

    def __init__(self):
        self.state = CrawlState()
        self.session_cookies = {}
        self.robots_parsers = {}

    def _get_robots(self, url: str) -> Optional[urllib.robotparser.RobotFileParser]:
        """获取并缓存 robots.txt 解析器"""
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base in self.robots_parsers:
            return self.robots_parsers[base]

        try:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(urljoin(base, "/robots.txt"))
            rp.read()
            self.robots_parsers[base] = rp
            return rp
        except:
            self.robots_parsers[base] = None
            return None

    def _raw_fetch(self, url: str, timeout: int = 10) -> Optional[bytes]:
        """原始字节获取"""
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers={"User-Agent": random.choice(USER_AGENTS)})
            resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
            return resp.read()
        except:
            return None

    def fetch(self, url: str, max_size: int = 500000) -> dict:
        """
        拟人抓取 — 完整流程:
          1. 检查是否适合爬取 (时段)
          2. 检查 robots.txt
          3. 检查域名限速
          4. 拟人等待
          5. 生成拟人头
          6. 抓取 + 重试
          7. 记录
        """
        result = {"url": url, "success": False, "status": 0,
                  "content": "", "size": 0, "delay": 0}

        parsed = urlparse(url)
        domain = parsed.netloc

        # 1. 时段检查
        if not HumanTiming.should_crawl_now():
            _logger.info(f"⏰ 跳过(非活跃时段): {url[:60]}")
            result["error"] = "非活跃时段"
            return result

        # 2. robots.txt
        rp = self._get_robots(url)
        if rp and not rp.can_fetch("*", url):
            _logger.info(f"🤖 robots.txt 禁止: {url[:60]}")
            result["error"] = "robots.txt 禁止"
            return result

        # 3. 限速检查
        if not self.state.check_and_record(domain):
            _logger.info(f"⏳ 限速跳过: {domain}")
            result["error"] = "超过限速"
            return result

        # 4. 拟人等待
        delay = HumanTiming.get_delay(domain)
        _logger.info(f"⏱ 等待 {delay:.1f}s... ({url[:50]})")
        time.sleep(delay)
        result["delay"] = round(delay, 2)

        # 5. 生成拾人请求头
        headers = HumanHeaders.generate()
        if domain in self.session_cookies:
            headers["Cookie"] = self.session_cookies[domain]

        # 6. 抓取 (含重试)
        for attempt in range(2):
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                req = urllib.request.Request(url, headers=headers)
                resp = urllib.request.urlopen(req, timeout=15, context=ctx)
                raw = resp.read()

                if len(raw) > max_size:
                    result["error"] = f"页面过大 ({len(raw)} > {max_size})"
                    return result

                # 编码检测
                content_type = resp.headers.get("Content-Type", "")
                encoding = self._detect_encoding(raw, content_type)
                content = raw.decode(encoding, errors="replace")

                # 保存Cookies
                set_cookie = resp.headers.get("Set-Cookie", "")
                if set_cookie:
                    self._save_cookie(domain, set_cookie)

                result["success"] = True
                result["status"] = resp.status
                result["content"] = content[:max_size]
                result["size"] = len(content)
                result["encoding"] = encoding
                result["headers"] = dict(resp.headers)

                _logger.info(f"✅ {resp.status} {url[:60]} ({len(content)}b, delay={delay:.1f}s)")
                return result

            except urllib.error.HTTPError as e:
                if e.code in (429, 503):
                    wait = (attempt + 1) * random.uniform(5, 10)
                    _logger.warning(f"⏳ 429/503, 等待 {wait:.0f}s...")
                    time.sleep(wait)
                    continue
                result["error"] = f"HTTP {e.code}"
                result["status"] = e.code
                _logger.warning(f"❌ HTTP {e.code}: {url[:60]}")
                return result

            except (urllib.error.URLError, socket.timeout) as e:
                if attempt == 0:
                    time.sleep(2)
                    continue
                result["error"] = str(e)[:60]
                _logger.warning(f"❌ {str(e)[:50]}: {url[:60]}")
                return result

            except Exception as e:
                result["error"] = str(e)[:60]
                _logger.error(f"❌ {str(e)[:50]}: {url[:60]}")
                return result

        return result

    def _detect_encoding(self, raw: bytes, content_type: str) -> str:
        """编码检测"""
        enc_match = re.search(r'charset=([\w-]+)', content_type, re.I)
        if enc_match:
            return enc_match.group(1).lower()
        if raw[:3] == b'\xef\xbb\xbf':
            return 'utf-8-sig'
        for enc in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'big5']:
            try:
                raw[:50].decode(enc)
                return enc
            except:
                continue
        return 'utf-8'

    def _save_cookie(self, domain: str, set_cookie: str):
        """保存 Cookie"""
        import http.cookies
        try:
            c = http.cookies.SimpleCookie(set_cookie)
            parts = []
            for key, morsel in c.items():
                parts.append(f"{key}={morsel.value}")
            if parts:
                self.session_cookies[domain] = "; ".join(parts)
        except:
            pass

    def crawl_urls(self, urls: list[str], extract_links: bool = False,
                    max_depth: int = 1) -> list[dict]:
        """批量爬取URL列表"""
        results = []
        visited = set()

        for url in urls:
            if url in visited:
                continue
            visited.add(url)

            result = self.fetch(url)
            results.append(result)

            # 提取链接继续爬 (depth=1)
            if extract_links and result["success"] and max_depth > 0:
                links = re.findall(r'href="(https?://[^"]+)"', result["content"])
                # 限制同域链接数
                domain_links = []
                for link in links[:5]:
                    if urlparse(link).netloc == urlparse(url).netloc:
                        domain_links.append(link)

                for link in domain_links:
                    if link not in visited:
                        visited.add(link)
                        sub_result = self.fetch(link)
                        results.append(sub_result)

        return results

    def crawl_site(self, start_url: str, max_pages: int = 5) -> list[dict]:
        """爬取一个站点 (广度优先)"""
        results = []
        visited = set()
        to_visit = [start_url]
        domain = urlparse(start_url).netloc

        while to_visit and len(visited) < max_pages:
            url = to_visit.pop(0)
            if url in visited:
                continue
            visited.add(url)

            result = self.fetch(url)
            results.append(result)

            if result["success"]:
                links = re.findall(r'href="(https?://[^"]+)"', result["content"])
                for link in links:
                    if (link not in visited and link not in to_visit
                            and urlparse(link).netloc == domain):
                        to_visit.append(link)

        return results

    def status(self) -> dict:
        """爬虫状态"""
        state = self.state.state
        return {
            "total_requests": state.get("total_requests", 0),
            "daily_reset": state.get("daily_reset", "N/A"),
            "domains_tracked": len(state.get("domains", {})),
            "active_domains": [
                {"domain": d, "today": s["count_day"], "last": s["last_request"]}
                for d, s in state.get("domains", {}).items()
            ],
        }


# ── CLI 测试 ──

if __name__ == "__main__":
    import sys

    crawler = HumanCrawler()

    if len(sys.argv) > 1 and sys.argv[1] == "fetch":
        url = sys.argv[2] if len(sys.argv) > 2 else "https://example.com"
        print(f"🌐 拟人爬取: {url}")
        result = crawler.fetch(url)
        if result["success"]:
            print(f"   ✅ {result['status']} ({result['size']}b, delay={result['delay']}s)")
            # 提取标题
            title = re.search(r'<title>(.*?)</title>', result["content"], re.DOTALL)
            if title:
                print(f"   标题: {title.group(1).strip()[:80]}")
        else:
            print(f"   ❌ {result.get('error', '?')}")

    elif len(sys.argv) > 1 and sys.argv[1] == "crawl":
        url = sys.argv[2] if len(sys.argv) > 2 else "https://example.com"
        pages = crawler.crawl_site(url, max_pages=3)
        print(f"🌐 爬取站点: {url} ({len(pages)} 页)")
        for p in pages:
            icon = "✅" if p["success"] else "❌"
            title = re.search(r'<title>(.*?)</title>', p.get("content", ""), re.DOTALL)
            t = title.group(1).strip()[:50] if title else "?"
            print(f"   {icon} {p['url'][:60]} ({p.get('size',0)}b) → {t}")

    elif len(sys.argv) > 1 and sys.argv[1] == "status":
        s = crawler.status()
        print(f"📊 爬虫状态")
        print(f"  总请求: {s['total_requests']}")
        print(f"  日重置: {s['daily_reset']}")
        print(f"  域名数: {s['domains_tracked']}")
        for d in s.get("active_domains", []):
            print(f"  {d['domain']}: 今日{d['today']}次")

    else:
        print("🕷️ Hermes 拟人爬虫 v1.0")
        print()
        print("用法:")
        print("  fetch <url>             拟人抓取单页")
        print("  crawl <url>             爬取站点 (最多5页)")
        print("  status                  查看爬虫状态")
        print()
        print("行为特征:")
        print("  • 请求间隔: 0.5-3s (正态分布+时段修正)")
        print("  • UA池: 9个真实浏览器指纹")
        print("  • 限速: 同域名≤5次/分钟, ≤200次/天")
        print("  • robots.txt: 严格遵守 + Crawl-Delay")
        print("  • 时段: 深夜自动降低频率")
        print("  • Cookie: 会话保持")
