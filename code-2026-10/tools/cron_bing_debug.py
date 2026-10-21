#!/usr/bin/env python3
"""Debug: dump raw Bing RSS response."""
import urllib.request, urllib.parse

q = "test query"
url = "https://cn.bing.com/search?q=" + urllib.parse.quote(q) + "&format=rss&count=5"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0"})
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read()
        print("STATUS:", r.status)
        print("CTYPE:", r.headers.get("Content-Type"))
        print("LEN:", len(data))
        print(data[:2000].decode("utf-8", "ignore"))
except Exception as e:
    print("ERR:", e)
