#!/usr/bin/env python3
"""Parse saved HTML files: GitHub trending, thepaper, arxiv mirror. Usage: python cron_parse_all.py"""
import re, html, os, json

BASE = os.path.dirname(os.path.abspath(__file__))
TMP = os.path.join(BASE, "tmp")

def parse_github_trending():
    src = os.path.join(TMP, "trending.html")
    if not os.path.exists(src):
        print("[GH] no file"); return
    data = open(src, encoding="utf-8", errors="ignore").read()
    articles = re.findall(r'<article class="Box-row[^"]*">(.*?)</article>', data, re.S)
    print("=== GITHUB TRENDING (%d) ===" % len(articles))
    for a in articles:
        m = re.search(r'<h2[^>]*>.*?href="/([^"]+)"[^>]*>(.*?)</a>', a, re.S)
        if not m:
            continue
        repo = m.group(1).strip()
        stars = re.search(r'([\d,\.]+[km]?)\s*</span>\s*</a>\s*</span>\s*</div>\s*<div class="f6', a, re.S)
        star_txt = stars.group(1) if stars else ""
        desc = ""
        m2 = re.search(r'<p[^>]*class="col-9[^"]*"[^>]*>(.*?)</p>', a, re.S)
        if m2:
            desc = html.unescape(re.sub(r"<[^>]+>", "", m2.group(1))).strip()
        lang = re.search(r'itemprop="programmingLanguage">([^<]+)<', a)
        lang = lang.group(1).strip() if lang else ""
        print(f"{repo} | {star_txt} | {lang} | {desc[:110]}")

def parse_thepaper():
    src = os.path.join(TMP, "thepaper.html")
    if not os.path.exists(src):
        print("[TP] no file"); return
    data = open(src, encoding="utf-8", errors="ignore").read()
    # thepaper homepage: news items in <a> with titles
    print("\n=== THEPAPER TOP NEWS ===")
    # look for index_news / headline links
    seen = set()
    for m in re.finditer(r'<a[^>]+href="(/newsDetail_forward_\d+)"[^>]*>(.*?)</a>', data, re.S):
        url, txt = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        txt = html.unescape(re.sub(r"\s+", " ", txt)).strip()
        if txt and txt not in seen and len(txt) > 8:
            seen.add(txt)
            print(f"https://www.thepaper.cn{url} | {txt[:80]}")
        if len(seen) >= 25:
            break

def parse_arxiv_mirror():
    src = os.path.join(TMP, "arxiv_mirror.html")
    if not os.path.exists(src):
        print("[AX] no file"); return
    data = open(src, encoding="utf-8", errors="ignore").read()
    print("\n=== ARXIV MIRROR PAPERS ===")
    # my-Arxiv-Daily static pages: look for paper titles in <a href="...arxiv.org/abs/...">
    seen = set()
    for m in re.finditer(r'<a[^>]+href="(https?://[^"]*arxiv\.org/abs/([^"]+))"[^>]*>(.*?)</a>', data, re.S):
        url, aid, txt = m.group(1), m.group(2), re.sub(r"<[^>]+>", "", m.group(3))
        txt = html.unescape(re.sub(r"\s+", " ", txt)).strip()
        if txt and aid not in seen:
            seen.add(aid)
            print(f"{aid} | {txt[:110]}")
        if len(seen) >= 30:
            break

if __name__ == "__main__":
    parse_github_trending()
    parse_thepaper()
    parse_arxiv_mirror()
