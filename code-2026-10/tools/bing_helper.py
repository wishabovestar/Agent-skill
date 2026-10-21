#!/usr/bin/env python3
"""Bing CN search helper: returns title/link/snippet from cn.bing.com HTML."""
import re, sys, html, json, urllib.parse, subprocess

def bing(q, count=15, mkt="zh-CN"):
    url = "https://cn.bing.com/search?q=%s&count=%d&mkt=%s&setlang=en" % (
        urllib.parse.quote(q), count, mkt)
    out = subprocess.run(
        ["curl", "-s", "-L", "-m", "30", "-A",
         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
         "-H", "Accept-Language: en-US,en;q=0.9", url],
        capture_output=True)
    raw = out.stdout
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            txt = raw.decode(enc); break
        except Exception:
            continue
    res = []
    # Bing organic results live in <li class="b_algo"> ... <h2><a href="...">Title</a></h2> <p>snippet</p>
    for block in re.findall(r'<li class="b_algo".*?</li>', txt, re.S):
        m = re.search(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        link = html.unescape(m.group(1))
        title = html.unescape(re.sub(r'<[^>]+>', '', m.group(2))).strip()
        sn = re.search(r'<p[^>]*>(.*?)</p>', block, re.S)
        snippet = html.unescape(re.sub(r'<[^>]+>', '', sn.group(1))).strip() if sn else ""
        res.append({"title": title, "url": link, "snippet": snippet[:300]})
    return res

if __name__ == "__main__":
    for q in sys.argv[1:]:
        print("=" * 100)
        print("QUERY:", q)
        r = bing(q)
        if not r:
            print("  (no organic results parsed)")
        for i, x in enumerate(r, 1):
            print("%2d. %s" % (i, x["title"]))
            print("    %s" % x["url"])
            if x["snippet"]:
                print("    %s" % x["snippet"])
