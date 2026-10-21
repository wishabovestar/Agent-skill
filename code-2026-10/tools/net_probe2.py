#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round 2 probe: correct RSS/feed paths for AI labs, with real HTTP error codes.

Usage:  python net_probe2.py direct|socks5
"""
import ssl
import socket
import sys
import time
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# name, url, kind  (kind: rss = feed to parse directly, html = page to scrape)
TARGETS = [
    # --- verified-reachable last round ---
    ("arxiv-api",        "https://export.arxiv.org/api/query?search_query=cat:cs.AI&max_results=1", "rss"),
    ("openai-news-rss",  "https://openai.com/news/rss.xml", "rss"),
    ("deepmind-blog",    "https://deepmind.google/discover/blog/", "html"),
    ("qwen-rss",         "https://qwenlm.github.io/blog/index.xml", "rss"),
    ("deepseek-news",    "https://api-docs.deepseek.com/news/", "html"),
    ("moonshot",         "https://moonshotai.github.io/", "html"),
    ("msr-feed",         "https://www.microsoft.com/en-us/research/blog/feed/", "rss"),
    ("cohere-blog",      "https://cohere.com/blog", "html"),
    ("baai-hub",         "https://hub.baai.ac.cn/", "html"),
    # --- new candidate feed paths ---
    ("anthropic-rss2",   "https://www.anthropic.com/news.rss", "rss"),
    ("anthropic-rss3",   "https://www.anthropic.com/rss/news.xml", "rss"),
    ("anthropic-eng",    "https://www.anthropic.com/engineering", "html"),
    ("google-blog-ai",   "https://blog.google/technology/ai/rss/", "rss"),
    ("google-research",  "https://research.google/blog/rss/", "rss"),
    ("deepmind-rss",     "https://deepmind.google/blog/rss.xml", "rss"),
    ("meta-ai-rss",      "https://ai.meta.com/blog/rss/", "rss"),
    ("mistral-feed",     "https://mistral.ai/feed.xml", "rss"),
    ("mistral-news",     "https://mistral.ai/news", "html"),
    ("huggingface",      "https://huggingface.co/blog/feed.xml", "rss"),
    ("hf-mirror",        "https://hf-mirror.com/blog/feed.xml", "rss"),
    ("nvidia-blog",      "https://blogs.nvidia.com/feed/", "rss"),
    ("xai-news",         "https://x.ai/news", "html"),
    ("ai2-blog",         "https://allenai.org/blog", "html"),
    ("together-blog",    "https://www.together.ai/blog", "html"),
    ("stability",        "https://stability.ai/news", "html"),
    ("bytedance-seed",   "https://seed.bytedance.com/en/blog", "html"),
    ("minimax",          "https://www.minimaxi.com/news", "html"),
    ("stepfun",          "https://www.stepfun.com/", "html"),
    ("baidu-ernie",      "https://ernie.baidu.com/blog/", "html"),
    ("01ai",             "https://www.01.ai/", "html"),
    ("openrouter",       "https://openrouter.ai/announcements", "html"),
]


def build_opener_socks5(host="127.0.0.1", port=10808):
    import socks  # PySocks
    socks.set_default_proxy(socks.SOCKS5, host, port)
    socket.socket = socks.socksocket
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def probe(url, timeout=15):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            body = r.read(8192)
            return ("OK", r.status, len(body), round(time.time() - t0, 2))
    except urllib.error.HTTPError as e:
        return (f"HTTP{e.code}", e.code, 0, round(time.time() - t0, 2))
    except Exception as e:  # noqa: BLE001
        return (type(e).__name__, 0, 0, round(time.time() - t0, 2))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "direct"
    print(f"### mode={mode}")
    if mode == "socks5":
        try:
            build_opener_socks5()
        except Exception as e:  # noqa: BLE001
            print("socks5 setup failed:", e)
            return
    ok = []
    for name, url, kind in TARGETS:
        st, code, n, dt = probe(url)
        flag = "OK " if st == "OK" else "FAIL"
        if st == "OK":
            ok.append((name, url, kind))
        print(f"{flag} {name:18s} {st:14s} http={code:<4} {n:>5}B {dt:>6}s  [{kind}] {url}")
    print(f"\n### reachable: {len(ok)}/{len(TARGETS)}")
    for n, u, k in ok:
        print(f"   {n}\t{k}\t{u}")


if __name__ == "__main__":
    main()
