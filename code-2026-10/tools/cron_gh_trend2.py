#!/usr/bin/env python3
"""Parse GitHub trending with star counts."""
import re, html, os

src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp", "trending.html")
data = open(src, encoding="utf-8", errors="ignore").read()
articles = re.findall(r'<article class="Box-row[^"]*">(.*?)</article>', data, re.S)
print("GITHUB TRENDING:", len(articles))
for a in articles:
    m = re.search(r'<h2[^>]*>.*?href="/([^"]+)"', a, re.S)
    if not m:
        continue
    repo = m.group(1).strip()
    # stars: look for repo-stars-counter-star span
    m2 = re.search(r'id="repo-stars-counter-star"[^>]*title="([^"]+)"', a)
    stars = m2.group(1) if m2 else ""
    m3 = re.search(r'id="repo-language-color"[^>]*>\s*</span>\s*([^<]+)<', a)
    lang = m3.group(1).strip() if m3 else ""
    m4 = re.search(r'<p[^>]*class="col-9[^"]*"[^>]*>(.*?)</p>', a, re.S)
    desc = html.unescape(re.sub(r"<[^>]+>", "", m4.group(1))).strip() if m4 else ""
    print(f"{repo} | stars:{stars} | {lang} | {desc[:100]}")
