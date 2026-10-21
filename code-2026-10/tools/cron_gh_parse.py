#!/usr/bin/env python3
"""Parse GitHub trending HTML into repo list."""
import re, html, os, sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp", "trending.html")

def main():
    if not os.path.exists(SRC):
        print("NO FILE"); return
    data = open(SRC, encoding="utf-8", errors="ignore").read()
    # Each trending repo is in an <article class="Box-row"> block
    articles = re.findall(r'<article class="Box-row[^"]*">(.*?)</article>', data, re.S)
    print("FOUND ARTICLES:", len(articles))
    out = []
    for a in articles:
        m = re.search(r'href="/([^"]+)"[^>]*>\s*<h2', a)
        if not m:
            m = re.search(r'<h2[^>]*>.*?href="/([^"]+)"', a, re.S)
        repo = m.group(1) if m else "?"
        m2 = re.search(r'<p[^>]*>(.*?)</p>', a, re.S)
        desc = html.unescape(re.sub(r"<[^>]+>", "", m2.group(1))).strip() if m2 else ""
        m3 = re.search(r'aria-label="([^"]*star[^"]*)"', a, re.I)
        stars = m3.group(1) if m3 else ""
        lang = re.search(r'itemprop="programmingLanguage">([^<]+)<', a)
        lang = lang.group(1).strip() if lang else ""
        out.append((repo, stars, lang, desc[:120]))
    for repo, stars, lang, desc in out:
        print(f"{repo} | {stars} | {lang} | {desc}")

if __name__ == "__main__":
    main()
