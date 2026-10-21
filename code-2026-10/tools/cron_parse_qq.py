#!/usr/bin/env python3
"""Extract readable text from saved QQ article HTML."""
import re, html, os

src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp", "qq_deepseek.html")
data = open(src, encoding="utf-8", errors="ignore").read()
# title
t = re.search(r"<title>(.*?)</title>", data, re.S)
print("TITLE:", html.unescape(t.group(1)).strip() if t else "?")
# main content paragraphs
paras = re.findall(r"<p[^>]*>(.*?)</p>", data, re.S)
txt = []
for p in paras:
    s = re.sub(r"<[^>]+>", "", p)
    s = html.unescape(re.sub(r"\s+", " ", s)).strip()
    if len(s) > 12:
        txt.append(s)
seen = set()
out = []
for s in txt:
    if s not in seen:
        seen.add(s)
        out.append(s)
print("\n".join(out[:40]))
