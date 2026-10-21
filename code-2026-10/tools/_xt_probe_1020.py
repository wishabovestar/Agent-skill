# -*- coding: utf-8 -*-
"""巡天更新 · 连接性探测（强制直连，规避 Windows 注册表代理 SSL EOF）"""
import ssl, sys, io, json, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=CTX),
)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

print("REG_PROXIES=", urllib.request.getproxies())

TESTS = [
    ("gh_api", "https://api.github.com/rate_limit"),
    ("gnews", "https://news.google.com/rss/search?q=%E9%94%82%E7%94%B5&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"),
    ("arxiv", "http://export.arxiv.org/api/query?search_query=all:%22solid-state%20electrolyte%22&max_results=3&sortBy=submittedDate&sortOrder=descending"),
    ("bing", "https://cn.bing.com/news/search?q=%E9%94%82%E7%94%B5&format=rss"),
]

for name, url in TESTS:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept": "application/json,application/rss+xml,text/html,*/*"})
        with OPENER.open(req, timeout=25) as r:
            body = r.read()
        print(f"{name}: HTTP {r.status} bytes={len(body)}")
        if name == "gh_api":
            d = json.loads(body.decode("utf-8", "ignore"))
            print("  core_remaining=", d.get("resources", {}).get("core", {}).get("remaining"),
                  " search_remaining=", d.get("resources", {}).get("search", {}).get("remaining"))
    except Exception as e:
        print(f"{name}: FAIL {type(e).__name__} {str(e)[:120]}")
