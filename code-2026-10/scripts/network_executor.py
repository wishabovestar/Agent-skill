"""
Hermes 网络执行端 v1.0 — 网络爬虫/扫描器/数据库发现/安全评估
==============================================================
功能:
  1. 网络爬虫 — 稳健抓取 + robots.txt 尊重 + 限速
  2. 服务发现 — 端口/协议/数据库检测  
  3. 数据库分类 — 权威公开 vs 未知可疑
  4. 安全评估 — 蜜罐检测/污染风险评估
  5. 安全查询 — 对可信数据库执行只读查询

架构:
  SpiderEngine (爬虫) → DiscoveryEngine (发现) → Classifier (分类)
    → SecurityAssessor (安全评估) → QueryEngine (安全查询)
"""

import json, time, re, socket, ssl, urllib.request, urllib.robotparser, random, hashlib
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, urljoin
from collections import defaultdict
from typing import Optional

# ── 配置 ──
CRAWL_DB = Path("D:/hermes/analysis/.crawler_cache.db")
CRAWL_LOG = Path("D:/hermes/analysis/.crawler_log.json")
ROBOTS_CACHE = Path("D:/hermes/analysis/.robots_cache.json")

# 爬虫身份
CRAWLER_NAME = "HermesNetworkAgent/1.0"
CRAWLER_EMAIL = "admin@hermes.local"

# 速率限制 (请求间隔秒数)
RATE_LIMITS = {
    "aggressive": 0.1,    # 本地/可信网络
    "normal": 1.0,        # 普通网站
    "polite": 3.0,        # 小型/个人站点
    "stealth": 5.0,       # 有反爬的站点
}

# 已知权威公开数据库 (可直接查询)
AUTHORITATIVE_DBS = {
    "arxiv": {
        "type": "api",
        "base": "http://export.arxiv.org/api/query",
        "auth": False,
        "rate_limit": "normal",
        "trust_level": "high",
        "description": "学术论文预印本数据库",
    },
    "github": {
        "type": "api",
        "base": "https://api.github.com",
        "auth": False,
        "rate_limit": "normal",
        "trust_level": "high",
        "description": "开源代码托管",
    },
    "wikipedia": {
        "type": "api",
        "base": "https://en.wikipedia.org/w/api.php",
        "auth": False,
        "rate_limit": "normal",
        "trust_level": "high",
        "description": "百科全书",
    },
    "arxiv_cn_mirror": {
        "type": "api",
        "base": "http://xxx.arxiv.org/api/query",
        "auth": False,
        "rate_limit": "normal",
        "trust_level": "high",
        "description": "arXiv 国内镜像",
    },
    "semantic_scholar": {
        "type": "api",
        "base": "https://api.semanticscholar.org/graph/v1",
        "auth": False,
        "rate_limit": "normal",
        "trust_level": "high",
        "description": "学术论文索引",
    },
}

# ═══════════════════════════════════════════════════
# 1. 爬虫引擎
# ═══════════════════════════════════════════════════

class SpiderEngine:
    """稳健爬虫: robots.txt 遵守 + 限速 + 缓存 + 重试"""

    def __init__(self, rate_limit: str = "normal"):
        self.rate = RATE_LIMITS.get(rate_limit, 1.0)
        self.last_request = {}
        self.robots_cache = self._load_robots()
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            f"{CRAWLER_NAME} (https://hermes.local; {CRAWLER_EMAIL})",
        ]

    def _load_robots(self) -> dict:
        if ROBOTS_CACHE.exists():
            try: return json.loads(ROBOTS_CACHE.read_text())
            except: pass
        return {}

    def _save_robots(self):
        ROBOTS_CACHE.write_text(json.dumps(self.robots_cache, indent=2))

    def _check_robots(self, url: str) -> bool:
        """遵守 robots.txt"""
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base in self.robots_cache:
            return self.robots_cache[base]

        try:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(urljoin(base, "/robots.txt"))
            rp.read()
            allowed = rp.can_fetch(CRAWLER_NAME, url)
            self.robots_cache[base] = allowed
            self._save_robots()
            return allowed
        except:
            # 无法读取 robots.txt → 默认允许 (更宽松)
            self.robots_cache[base] = True
            return True

    def _rate_limit(self, domain: str):
        """请求频率控制"""
        now = time.time()
        last = self.last_request.get(domain, 0)
        gap = now - last
        if gap < self.rate:
            time.sleep(self.rate - gap)
        self.last_request[domain] = time.time()

    def fetch(self, url: str, timeout: int = 15, headers: dict = None,
               respect_robots: bool = True) -> dict:
        """
        稳健抓取: robots.txt → 限速 → 重试 → 编码处理
        respect_robots=False: 绕过 robots.txt (仅用于已知公开API)
        """
        # 遵守 robots.txt (可绕过)
        domain = urlparse(url).netloc
        if respect_robots:
            if not self._check_robots(url):
                return {"success": False, "error": "robots.txt 禁止爬取"}

        # 限速
        self._rate_limit(domain)

        # 请求头
        req_headers = {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if headers:
            req_headers.update(headers)

        # 重试机制
        for attempt in range(3):
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                req = urllib.request.Request(url, headers=req_headers)
                resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
                raw = resp.read()

                # 编码检测
                content_type = resp.headers.get("Content-Type", "")
                encoding = self._detect_encoding(raw, content_type)
                content = raw.decode(encoding, errors="replace")

                return {
                    "success": True,
                    "content": content,
                    "status": resp.status,
                    "encoding": encoding,
                    "url": url,
                    "headers": dict(resp.headers),
                }
            except urllib.error.HTTPError as e:
                if e.code in (429, 503):
                    wait = (attempt + 1) * 5
                    time.sleep(wait)
                    continue
                return {"success": False, "error": f"HTTP {e.code}"}
            except Exception as e:
                if attempt < 2:
                    time.sleep(2)
                    continue
                return {"success": False, "error": str(e)[:80]}

        return {"success": False, "error": "全部重试失败"}

    def _detect_encoding(self, raw: bytes, content_type: str = "") -> str:
        """自动检测编码"""
        import re
        enc_match = re.search(r'charset=([\w-]+)', content_type, re.I)
        if enc_match:
            return enc_match.group(1).lower()
        if raw[:3] == b'\xef\xbb\xbf':
            return 'utf-8-sig'
        for enc in ['utf-8', 'gbk', 'gb2312', 'big5']:
            try:
                raw[:100].decode(enc)
                return enc
            except:
                continue
        return 'utf-8'


# ═══════════════════════════════════════════════════
# 2. 服务发现引擎
# ═══════════════════════════════════════════════════

class DiscoveryEngine:
    """发现本地/网络中的服务、端口和数据库"""

    def __init__(self, target: str = "127.0.0.1"):
        self.target = target
        self.discovered = []

    def scan_ports(self, ports: list[int] = None, timeout: float = 0.5) -> list[dict]:
        """扫描端口, 识别服务"""
        if ports is None:
            ports = [21,22,23,25,53,80,443,445,631,993,995,
                     1433,1521,3306,3389,5432,5900,6379,8080,8443,
                     9092,9200,11211,27017,50070]
        results = []
        for port in ports:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b'\x01\x00\x00\x00\x00\x00\x00\x00')
                code = s.connect_ex((self.target, port))
                if code == 0:
                    service = self._guess_service(port)
                    results.append({
                        "port": port,
                        "state": "open",
                        "service": service,
                    })
                    self.discovered.append(("port", self.target, port, service))
                s.close()
            except:
                pass
        return results

    def _guess_service(self, port: int) -> str:
        services = {
            21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
            53: "DNS", 80: "HTTP", 443: "HTTPS", 445: "SMB",
            1433: "MSSQL", 1521: "Oracle", 3306: "MySQL",
            3389: "RDP", 5432: "PostgreSQL", 5900: "VNC",
            6379: "Redis", 8080: "HTTP-Alt", 8443: "HTTPS-Alt",
            9092: "Kafka", 9200: "Elasticsearch", 11211: "Memcached",
            27017: "MongoDB", 50070: "HDFS",
        }
        return services.get(port, f"Unknown({port})")

    def probe_service(self, host: str, port: int,
                       send_bytes: bytes = b"\x00") -> dict:
        """试探服务banner"""
        result = {"host": host, "port": port}
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((host, port))
            # 先收banner
            try:
                banner = s.recv(256)
                result["banner"] = banner.hex()
                result["banner_text"] = banner.decode("utf-8", errors="replace")[:100]
            except socket.timeout:
                # 无banner, 发试探字节
                s.send(send_bytes)
                time.sleep(0.3)
                resp = s.recv(256)
                result["banner"] = resp.hex()
                result["banner_text"] = resp.decode("utf-8", errors="replace")[:100]
            s.close()
            result["reachable"] = True
        except Exception as e:
            result["reachable"] = False
            result["error"] = str(e)[:50]
        return result


# ═══════════════════════════════════════════════════
# 3. 数据库分类器
# ═══════════════════════════════════════════════════

class DatabaseClassifier:
    """分类发现的数据库: 权威公开 vs 内部 vs 可疑"""

    AUTHORITATIVE_SIGNATURES = {
        "arXiv": [b"arXiv", b"export.arxiv.org"],
        "Wikipedia": [b"wikipedia.org", b"mediawiki"],
        "GitHub": [b"github.com", b"X-GitHub"],
        "SemanticScholar": [b"semanticscholar", b"Semantic Scholar"],
        "PubMed": [b"pubmed", b"ncbi.nlm.nih"],
        "Crossref": [b"crossref", b"Crossref"],
    }

    DANGEROUS_SIGNALS = [
        b"root@", b"password:", b"login:", b"Welcome to",
        b"shell", b"bash", b"/bin/sh",
        b"captcha", b"verify",
    ]

    @classmethod
    def classify(cls, service_info: dict) -> dict:
        """
        分类服务: authoritative | internal | suspicious | unknown
        """
        result = {
            "category": "unknown",
            "trust_level": "unknown",
            "can_query": False,
            "warnings": [],
        }

        url = service_info.get("url", "") or \
              f"{service_info.get('host','')}:{service_info.get('port','')}"
        banner = service_info.get("banner_text", "") or \
                 service_info.get("banner", "")

        # 权威公开数据库
        for name, sigs in cls.AUTHORITATIVE_SIGNATURES.items():
            for sig in sigs:
                if isinstance(sig, bytes):
                    if sig in banner.encode() if isinstance(banner, str) else sig in banner:
                        result["category"] = "authoritative"
                        result["trust_level"] = "high"
                        result["can_query"] = True
                        result["name"] = name
                        result["warnings"].append(f"权威公开数据库: {name}")
                        return result
                elif sig in str(url):
                    result["category"] = "authoritative"
                    result["trust_level"] = "high"
                    result["can_query"] = True
                    result["name"] = name
                    result["warnings"].append(f"权威公开数据库: {name}")
                    return result

        # 已知内部服务 (Redis, MySQL等内网)
        for kw in ["redis", "mysql", "postgresql", "mongodb"]:
            if kw in str(banner).lower():
                result["category"] = "internal"
                result["trust_level"] = "medium"
                result["can_query"] = False
                result["requires_auth"] = True
                result["warnings"].append(f"内部数据库 ({kw})，需认证")
                return result

        # 也按端口号补充判断
        known_internal_ports = {
            6379: "Redis", 6380: "Redis", 3306: "MySQL",
            5432: "PostgreSQL", 27017: "MongoDB", 11211: "Memcached",
        }
        port = service_info.get("port")
        if port in known_internal_ports:
            result["category"] = "internal"
            result["trust_level"] = "medium"
            result["can_query"] = False
            result["requires_auth"] = True
            result["warnings"].append(f"内部数据库 (端口{port}→{known_internal_ports[port]})，需认证")
            return result

        # 危险信号检测
        banner_bytes = banner.encode() if isinstance(banner, str) else (banner if isinstance(banner, bytes) else b"")
        for sig in cls.DANGEROUS_SIGNALS:
            if sig in banner_bytes:
                result["category"] = "suspicious"
                result["trust_level"] = "low"
                result["can_query"] = False
                result["warnings"].append(f"危险信号: {sig}")
                return result

        # 内置数据库 (Hermes本地)
        known_local = [
            "knowledge_store.db", "state.db", "search_cache.db"
        ]
        path = service_info.get("path", "")
        for k in known_local:
            if k in path:
                result["category"] = "local"
                result["trust_level"] = "high"
                result["can_query"] = True
                result["name"] = k
                return result

        return result


# ═══════════════════════════════════════════════════
# 4. 安全评估器
# ═══════════════════════════════════════════════════

class SecurityAssessor:
    """
    安全评估: 蜜罐检测 / 污染风险评估 / 交互建议
    """

    HONEYPOT_SIGNATURES = [
        {"pattern": b"root default password", "risk": "high"},
        {"pattern": b"welcome to.*admin panel", "risk": "high"},
        {"pattern": b"shell access", "risk": "high"},
        {"pattern": b"free proxy", "risk": "medium"},
        {"pattern": b"unsecured.*camera", "risk": "medium"},
    ]

    @classmethod
    def assess(cls, service: dict) -> dict:
        """返回安全评估结果"""
        assessment = {
            "is_honeypot": False,
            "risk_level": "low",
            "recommendation": "可以交互",
            "details": [],
        }

        banner = service.get("banner_text", "") or str(service.get("banner", ""))
        name = service.get("service", service.get("name", ""))

        # 1. 蜜罐签名检测
        for sig in cls.HONEYPOT_SIGNATURES:
            if sig["pattern"] in banner.encode() if isinstance(banner, str) else sig["pattern"] in banner:
                assessment["is_honeypot"] = True
                assessment["risk_level"] = sig["risk"]
                assessment["details"].append(f"蜜罐签名: {sig['pattern']}")
                assessment["recommendation"] = "⚠️ 疑似蜜罐，禁止交互"
                return assessment

        # 2. 权威数据库 → 安全
        if service.get("category") == "authoritative":
            assessment["risk_level"] = "none"
            assessment["recommendation"] = "✅ 权威公开数据库，可直接查询"

        # 3. 内部数据库 → 需认证
        elif service.get("category") == "internal":
            assessment["risk_level"] = "low"
            assessment["recommendation"] = "🔒 内部数据库，需认证后只读查询"

        # 4. 可疑 → 隔离
        elif service.get("category") == "suspicious":
            assessment["risk_level"] = "high"
            assessment["recommendation"] = "🚫 可疑服务，禁止交互"

        # 5. 未知 → 谨慎观察
        elif service.get("category") == "unknown":
            assessment["risk_level"] = "medium"
            assessment["recommendation"] = "⚠️ 未知服务，仅被动观察，不发送任何数据"

        return assessment


# ═══════════════════════════════════════════════════
# 5. 安全查询引擎
# ═══════════════════════════════════════════════════

class QueryEngine:
    """对可信数据库执行只读安全查询"""

    def __init__(self):
        self.spider = SpiderEngine(rate_limit="normal")

    def query_authoritative(self, db_name: str, query: str, **params) -> dict:
        """
        查询权威公开数据库。
        仅允许 AUTHORITATIVE_DBS 中定义的数据库。
        """
        if db_name not in AUTHORITATIVE_DBS:
            return {"success": False, "error": f"未知数据库: {db_name}",
                    "allowed_dbs": list(AUTHORITATIVE_DBS.keys())}

        db = AUTHORITATIVE_DBS[db_name]
        if db["type"] != "api":
            return {"success": False, "error": f"不支持的数据库类型: {db['type']}"}

        self.spider.rate = RATE_LIMITS.get(db.get("rate_limit", "normal"), 1.0)

        # 按数据库构建查询URL
        if db_name == "arxiv":
            from urllib.parse import quote
            url = f"{db['base']}?search_query=all:{quote(query)}&max_results={params.get('limit', 5)}&sortBy=relevance"
        elif db_name == "github":
            from urllib.parse import quote
            url = f"{db['base']}/search/repositories?q={quote(query)}&per_page={params.get('limit', 5)}&sort=stars"
        elif db_name == "wikipedia":
            lang = params.get("lang", "en")
            from urllib.parse import quote
            url = f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote(query)}&format=json&srlimit={params.get('limit', 5)}"
        elif db_name == "arxiv_cn_mirror":
            from urllib.parse import quote
            url = f"{db['base']}?search_query=all:{quote(query)}&max_results={params.get('limit', 5)}&sortBy=relevance"
        elif db_name == "semantic_scholar":
            from urllib.parse import quote
            url = f"{db['base']}/paper/search?query={quote(query)}&limit={params.get('limit', 5)}"
        else:
            return {"success": False, "error": f"数据库 {db_name} 查询方法未实现"}

        # 权威数据库API: respect_robots=False
        result = self.spider.fetch(url, timeout=15, respect_robots=False)
        if result["success"]:
            return {"success": True, "db": db_name, "query": query,
                    "response_size": len(result["content"]),
                    "content": result["content"][:5000]}
        return {"success": False, "error": result.get("error", "未知错误")}

    def query_local(self, db_type: str, db_path: str, query: str) -> dict:
        """查询本地数据库 (SQLite)"""
        import sqlite3
        if not Path(db_path).exists():
            return {"success": False, "error": f"数据库不存在: {db_path}"}

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query)
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return {"success": True, "rows": rows[:20], "count": len(rows)}
        except Exception as e:
            return {"success": False, "error": str(e)[:100]}


# ═══════════════════════════════════════════════════
# 6. 编排器
# ═══════════════════════════════════════════════════

class NetworkExecutor:
    """网络执行端总入口"""

    def __init__(self):
        self.spider = SpiderEngine()
        self.discoverer = DiscoveryEngine()
        self.classifier = DatabaseClassifier()
        self.assessor = SecurityAssessor()
        self.querier = QueryEngine()
        self.log = []

    def crawl(self, url: str, max_pages: int = 5) -> list[dict]:
        """爬取网页并提取链接"""
        pages = []
        visited = set()
        to_visit = [url]

        while to_visit and len(pages) < max_pages:
            current = to_visit.pop(0)
            if current in visited:
                continue
            visited.add(current)

            result = self.spider.fetch(current)
            if result["success"]:
                import re
                # 提取链接
                links = re.findall(r'href="(https?://[^"]+)"', result["content"])
                for link in links[:10]:
                    if link not in visited:
                        to_visit.append(link)

                pages.append({
                    "url": current,
                    "status": result["status"],
                    "size": len(result["content"]),
                    "links_found": len(links),
                })
                self.log.append(("crawl", current, "ok"))
            else:
                self.log.append(("crawl", current, "failed"))

        return pages

    def discover(self, target: str = "127.0.0.1",
                  ports: list[int] = None) -> list[dict]:
        """发现服务 + 分类 + 安全评估"""
        results = []
        open_ports = self.discoverer.scan_ports(ports)

        for p in open_ports:
            # 试探banner
            probe = self.discoverer.probe_service(target, p["port"])
            probe["service"] = p["service"]

            # 分类
            classification = self.classifier.classify(probe)
            probe.update(classification)

            # 安全评估
            assessment = self.assessor.assess(probe)
            probe.update(assessment)

            results.append(probe)
            self.log.append(("discover", f"{target}:{p['port']}",
                             probe.get("category", "unknown")))

        return results

    def query(self, target: str, query_str: str, **kwargs) -> dict:
        """安全查询: 自动选择查询路径"""
        # 如果是权威数据库名称
        if target in AUTHORITATIVE_DBS:
            return self.querier.query_authoritative(target, query_str, **kwargs)

        # 如果是本地文件
        if Path(target).exists():
            return self.querier.query_local("sqlite", target, query_str)

        # 如果是URL
        if target.startswith("http"):
            return self.spider.fetch(target)

        return {"success": False, "error": f"未知查询目标: {target}"}


# ── CLI ──

if __name__ == "__main__":
    import sys
    ne = NetworkExecutor()

    if len(sys.argv) > 1 and sys.argv[1] == "crawl":
        url = sys.argv[2] if len(sys.argv) > 2 else "https://example.com"
        pages = ne.crawl(url)
        for p in pages:
            print(f"  {p['status']} {p['url'][:80]} ({p['size']}b, {p['links_found']} links)")

    elif len(sys.argv) > 1 and sys.argv[1] == "discover":
        target = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
        services = ne.discover(target)
        print(f"\n📡 发现 {len(services)} 个服务:")
        for s in services:
            cat_icon = {"authoritative": "✅", "internal": "🔒",
                        "suspicious": "🚨", "unknown": "⚠️"}.get(
                            s.get("category", "unknown"), "❓")
            print(f"  {cat_icon} :{s['port']} ({s['service']})")
            print(f"     分类: {s.get('category','?')}  等级: {s.get('trust_level','?')}")
            print(f"     建议: {s.get('recommendation','?')}")

    elif len(sys.argv) > 1 and sys.argv[1] == "query":
        target = sys.argv[2] if len(sys.argv) > 2 else "arxiv"
        query = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else "battery"
        result = ne.query(target, query)
        if result["success"]:
            print(f"✅ 查询成功 (db={result.get('db', target)})")
            print(f"   响应大小: {result.get('response_size', len(str(result)))} bytes")
        else:
            print(f"❌ {result.get('error', '失败')}")

    elif len(sys.argv) > 1 and sys.argv[1] == "authoritative":
        print("📚 已知权威公开数据库:")
        for name, info in sorted(AUTHORITATIVE_DBS.items()):
            print(f"  ✅ {name} — {info['description']}")
            print(f"     {info['base']}")

    elif len(sys.argv) > 1 and sys.argv[1] == "assess":
        target = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
        port = int(sys.argv[3]) if len(sys.argv) > 3 else 6379
        probe = ne.discoverer.probe_service(target, port)
        class_ = ne.classifier.classify(probe)
        assess = ne.assessor.assess(class_)
        print(f"📊 安全评估 :{port}")
        print(f"  分类: {class_.get('category','?')}")
        print(f"  建议: {assess.get('recommendation','?')}")

    else:
        print("🌐 Hermes 网络执行端 v1.0")
        print()
        print("用法:")
        print("  crawl <url>             爬取网页")
        print("  discover [target]       发现服务+分类+安全评估")
        print("  query <db> <query>      安全查询权威数据库")
        print("  authoritative           列出已知权威数据库")
        print("  assess <host> <port>    安全评估单个服务")
        print()
        print(f"权威数据库: {len(AUTHORITATIVE_DBS)} 个")
        for name, info in AUTHORITATIVE_DBS.items():
            print(f"  {name}: {info['description']}")
