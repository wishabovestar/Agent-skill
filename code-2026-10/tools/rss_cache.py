"""
网络预处理缓存器 — Cron 驱动
===================================
在空闲时段预取技术新闻，填充本地搜索缓存。
避免"刚好需要时才去搜 → 搜不到"的尴尬。

运行方式: cronjob(no_agent=true, script="rss_cache.py", schedule="every 4h")
"""

import json, time, sqlite3, hashlib, subprocess, re
from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus

CACHE_DB = str(Path("D:/hermes/analysis/search_cache.db"))

# 预取的 RSS 源（国内可达）
RSS_FEEDS = [
    # 百度热搜
    "https://top.baidu.com/board?tab=realtime",
    # RSSHub 镜像（国内可用实例）
    "https://rsshub.app/36kr/motif/ai",
    "https://rsshub.app/github/trending/daily",
    # Hugging Face Daily Papers
    "https://huggingface.co/papers",
    # 直接使用 curl 抓取
]

# 预搜索的关键词（电池领域+通用技术）
PRELOAD_QUERIES = [
    # 电池专用
    "锂电池 补锂技术 2025 2026",
    "硅碳负极 最新进展",
    "苹果 电池供应商 价格 2025",
    "压延补锂 工艺 设备",
    "Tata 电子 泄密 苹果 供应链",
    # 通用技术
    "Anthropic Claude 代码泄露 agent",
    "AI agent 自我迭代 改善",
]

def init_cache():
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS search_cache (
            query_hash TEXT PRIMARY KEY,
            category TEXT,
            result TEXT,
            created_at REAL,
            expires_at REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cache_stats (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    return conn


def fetch_page(url: str, timeout: int = 10) -> str | None:
    """抓取网页内容"""
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout), "-L", url,
             "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"],
            capture_output=True, timeout=timeout + 5
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.decode("utf-8", errors="replace")
    except:
        pass
    return None


def extract_baidu_hot(content: str) -> list:
    """解析百度热搜"""
    results = []
    items = re.findall(r'<div class="content_1YWBm">(.*?)</div>', content, re.DOTALL)
    for item in items[:20]:
        title = re.sub(r'<[^>]+>', '', item).strip()
        if title:
            results.append({"title": title, "source": "百度热搜"})
    return results


def cache_results(query: str, results: list, category: str = "web"):
    """写入缓存"""
    qhash = hashlib.md5(query.lower().encode()).hexdigest()
    now = time.time()
    ttl = {"web": 3600, "news": 1800, "academic": 86400}.get(category, 3600)

    data = json.dumps({"results": results, "count": len(results),
                       "source": "preload_cache", "cached_at": now},
                      ensure_ascii=False)

    conn = sqlite3.connect(CACHE_DB)
    conn.execute(
        "INSERT OR REPLACE INTO search_cache VALUES (?, ?, ?, ?, ?)",
        (qhash, category, data[:5000], now, now + ttl)
    )
    conn.commit()
    conn.close()


def main():
    conn = init_cache()
    stats = {"started_at": time.time(), "fetched": 0, "cached": 0, "errors": 0}

    print(f"📡 网络预处理缓存器 — {datetime.now().isoformat()}")
    print(f"   RSS源: {len(RSS_FEEDS)}")
    print(f"   预搜索关键词: {len(PRELOAD_QUERIES)}")
    print()

    # 尝试直连 Bing 搜索预加载
    for query in PRELOAD_QUERIES:
        try:
            encoded = quote_plus(query)
            # Bing CN
            url = f"https://cn.bing.com/search?q={encoded}&count=10"
            content = fetch_page(url)
            if content and len(content) > 1000:
                # 简易提取标题
                titles = re.findall(r'<h2>.*?<a[^>]*>(.*?)</a>', content, re.DOTALL)
                results = []
                for t in titles[:8]:
                    clean = re.sub(r'<[^>]+>', '', t).strip()
                    if clean:
                        results.append({"title": clean, "source": "Bing CN"})
                if results:
                    cache_results(query, results, "web")
                    stats["cached"] += 1
                    print(f"   ✅ 缓存 \"{query[:30]}...\" → {len(results)}条")
                else:
                    stats["errors"] += 1
                    print(f"   ⚠️ \"{query[:30]}...\" 提取结果为0")
            else:
                stats["errors"] += 1
                print(f"   ⚠️ \"{query[:30]}...\" 内容为空({len(content) if content else 0}bytes)")
        except Exception as e:
            stats["errors"] += 1
            print(f"   ❌ \"{query[:30]}...\" 失败: {str(e)[:50]}")

        stats["fetched"] += 1

    # 尝试抓取 RSS
    for feed_url in RSS_FEEDS[:2]:
        content = fetch_page(feed_url)
        if content and len(content) > 500:
            stats["cached"] += 1
            print(f"   ✅ RSS: {feed_url[:50]}... ({len(content)} bytes)")
        else:
            stats["errors"] += 1

    # 写状态
    stats["finished_at"] = time.time()
    stats["duration_s"] = round(stats["finished_at"] - stats["started_at"], 1)
    conn.execute("INSERT OR REPLACE INTO cache_stats VALUES (?, ?)",
                 ("last_run", json.dumps(stats)))
    conn.commit()
    conn.close()

    print()
    print(f"📊 完成: {stats['cached']} 缓存 / {stats['errors']} 错误 / {stats['duration_s']}s")
    print(f"   缓存DB: {CACHE_DB}")


if __name__ == "__main__":
    main()
