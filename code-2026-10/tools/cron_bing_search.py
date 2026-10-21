#!/usr/bin/env python3
"""Bing CN search via RSS (works behind GFW). Usage: python bing_search.py "query" [num_results]"""
import sys, re, html, urllib.request, urllib.parse, datetime, xml.etree.ElementTree as ET

def search(query, num=8, lang="zh-CN"):
    url = "https://cn.bing.com/search?q=" + urllib.parse.quote(query) + "&format=rss&count=%d&setlang=%s" % (num, lang)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read().decode("utf-8", "ignore")
    except Exception as e:
        return [("ERROR", str(e), "", "")]
    ns = {"": "http://www.w3.org/2005/Atom"}
    results = []
    try:
        root = ET.fromstring(data)
        items = root.findall(".//item") or root.findall(".//entry")
        for it in items[:num]:
            def g(tag):
                e = it.find(tag) or it.find("{http://www.w3.org/2005/Atom}" + tag)
                return e.text.strip() if e is not None and e.text else ""
            title = html.unescape(g("title"))
            link = g("link")
            desc = re.sub(r"<[^>]+>", " ", g("description"))
            desc = html.unescape(re.sub(r"\s+", " ", desc)).strip()
            pub = g("pubDate")
            results.append((title, link, desc, pub))
    except Exception as e:
        results.append(("PARSE_ERROR", str(e), data[:300], ""))
    return results

if __name__ == "__main__":
    q = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    for t, l, d, p in search(q, n):
        print(f"TITLE: {t}")
        print(f"URL: {l}")
        if p: print(f"DATE: {p}")
        if d: print(f"DESC: {d[:200]}")
        print("---")
