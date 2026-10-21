#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe reachability of the arXiv API and major AI-company blog endpoints.

Direct first, then via the local SOCKS5 proxy (xray 10808) if direct fails.
Reports a compact matrix so the collector can pick the working route.
"""
import socket
import ssl
import sys
import time
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

TARGETS = [
    ("arxiv-api",     "https://export.arxiv.org/api/query?search_query=cat:cs.AI&max_results=1"),
    ("arxiv-org",     "https://arxiv.org/abs/2401.00001"),
    ("openai",        "https://openai.com/news/rss.xml"),
    ("openai-blog",   "https://openai.com/blog"),
    ("anthropic",     "https://www.anthropic.com/news"),
    ("anthropic-rss", "https://www.anthropic.com/rss.xml"),
    ("deepmind",      "https://deepmind.google/discover/blog/"),
    ("meta-ai",       "https://ai.meta.com/blog/"),
    ("mistral",       "https://mistral.ai/news"),
    ("qwen",          "https://qwenlm.github.io/blog/index.xml"),
    ("deepseek",      "https://api-docs.deepseek.com/news/"),
    ("moonshot",      "https://moonshotai.github.io/"),
    ("zhipu",         "https://zhipuai.cn/"),
    ("baai",          "https://hub.baai.ac.cn/"),
    ("huggingface",   "https://huggingface.co/blog/feed.xml"),
    ("github-api",    "https://api.github.com/search/repositories?q=llm&per_page=1"),
    ("google-research","https://research.google/blog/"),
    ("microsoft-res", "https://www.microsoft.com/en-us/research/blog/feed/"),
    ("nvidia",        "https://blogs.nvidia.com/feed/"),
    ("cohere",        "https://cohere.com/blog"),
    ("ai2",           "https://allenai.org/blog"),
    ("xai",           "https://x.ai/news"),
]


def socks5_opener(host="127.0.0.1", port=10808):
    """Build an opener that tunnels through a SOCKS5 proxy using PySocks."""
    try:
        import socks  # PySocks
    except ImportError:
        return None, "PySocks not installed"
    socks.set_default_proxy(socks.SOCKS5, host, port)
    socket.socket = socks.socksocket  # global replacement, per project convention
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx)), None


def probe(url, timeout=12):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            body = r.read(4096)
            return ("OK", r.status, len(body), round(time.time() - t0, 2))
    except Exception as e:  # noqa: BLE001
        return (type(e).__name__, 0, 0, round(time.time() - t0, 2))


def proxy_port_open(host="127.0.0.1", port=10808, t=1.5):
    s = socket.socket()
    s.settimeout(t)
    try:
        s.connect((host, port))
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        s.close()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "direct"
    print(f"### mode={mode}")
    if mode == "socks5":
        if not proxy_port_open():
            print("SOCKS5 127.0.0.1:10808 NOT LISTENING -> abort")
            return
        _, err = socks5_opener()
        if err:
            print("proxy setup failed:", err)
            return
    for name, url in TARGETS:
        st, code, n, dt = probe(url)
        flag = "OK " if st == "OK" else "FAIL"
        print(f"{flag} {name:16s} {st:24s} http={code:<4} {n:>5}B {dt:>6}s  {url}")

    if mode != "socks5" and proxy_port_open():
        print("\n[note] xray SOCKS5 10808 IS listening -> retry failures with: python net_probe.py socks5")


if __name__ == "__main__":
    main()
