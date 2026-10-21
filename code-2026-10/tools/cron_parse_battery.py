#!/usr/bin/env python3
"""Extract headlines from saved battery news site HTML."""
import re, html, os

def extract(src, name, patterns):
    if not os.path.exists(src):
        print(f"[{name}] no file"); return
    data = open(src, encoding="utf-8", errors="ignore").read()
    print(f"\n=== {name} HEADLINES ===")
    seen = set()
    for pat in patterns:
        for m in re.finditer(pat, data, re.S):
            txt = re.sub(r"<[^>]+>", "", m.group(1) if m.lastindex else m.group(0))
            txt = html.unescape(re.sub(r"\s+", " ", txt)).strip()
            if txt and txt not in seen and len(txt) > 10:
                seen.add(txt)
                print(txt[:100])
            if len(seen) >= 30:
                return

BASE = os.path.dirname(os.path.abspath(__file__))
extract(os.path.join(BASE, "tmp", "itdcw.html"), "ITDCW(电池网)", [
    r'<a[^>]+href="[^"]*"[^>]*title="([^"]+)"',
    r'<a[^>]+title="([^"]+)"',
])
extract(os.path.join(BASE, "tmp", "cbcu.html"), "CBCU(中国电池工业协会)", [
    r'<a[^>]+href="[^"]*"[^>]*title="([^"]+)"',
    r'<a[^>]+title="([^"]+)"',
])
