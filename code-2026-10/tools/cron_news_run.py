#!/usr/bin/env python3
"""Cron news runner: runs all queries via Bing CN RSS, dumps results to tmp/news_results.txt"""
import sys, re, html, urllib.request, urllib.parse, datetime, xml.etree.ElementTree as ET, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp", "news_results.txt")

def search(query, num=6):
    url = "https://cn.bing.com/search?q=" + urllib.parse.quote(query) + "&format=rss&count=%d&setlang=zh-CN" % num
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    })
    results = []
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read().decode("utf-8", "ignore")
        root = ET.fromstring(data)
        items = root.findall(".//item")
        if not items:
            items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for it in items[:num]:
            def g(tag, attr=None):
                e = it.find(tag)
                if e is None:
                    e = it.find("{http://www.w3.org/2005/Atom}" + tag)
                if e is None:
                    return ""
                if attr:
                    return e.get(attr, "") or ""
                return e.text.strip() if e.text else ""
            title = html.unescape(g("title"))
            link = g("link", "href") or g("link")
            desc = re.sub(r"<[^>]+>", " ", g("description"))
            desc = html.unescape(re.sub(r"\s+", " ", desc)).strip()
            pub = g("pubDate")
            if title or link:
                results.append((title, link, desc[:220], pub))
    except Exception as e:
        results.append(("QUERY_ERROR", str(e), query, ""))
    return results

QUERIES = {
    "VIRUS": [
        "COVID-19 新变种 世界卫生组织 最新通报",
        "新冠 疫情 最新 中疾控 变异株",
        "influenza H5N1 bird flu WHO update August 2026",
        "流感 疫情 最新 2026年8月",
    ],
    "AI": [
        "AI 大模型 发布 最新 2026年8月",
        "OpenAI Anthropic Google new AI model August 2026",
        "人工智能 重大突破 本周 2026",
    ],
    "BATTERY": [
        "固态电池 最新进展 2026年8月",
        "碳酸锂 价格 2026年8月",
        "lithium battery solid state silicon anode arxiv 2026",
        "锂电池 新技术 论文 2026",
    ],
    "PAPERS": [
        "arxiv transformer diffusion paper August 2026",
        "arxiv large language model new paper 2026",
        "arxiv reinforcement learning new paper 2026",
    ],
    "TECHFIN": [
        "半导体 芯片 最新 政策 2026年8月",
        "科技公司 财报 Q2 2026",
        "新能源 政策 中国 2026年8月",
        "NVIDIA TSMC earnings August 2026",
    ],
}

def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("=== NEWS DUMP %s ===\n" % datetime.datetime.now().isoformat())
        for section, qs in QUERIES.items():
            for q in qs:
                f.write("\n### [%s] QUERY: %s\n" % (section, q))
                for t, l, d, p in search(q):
                    f.write("TITLE: %s\nURL: %s\nDESC: %s\nDATE: %s\n---\n" % (t, l, d, p))
                f.write("===ENDQ===\n")
                print("done:", section, q[:40])
    print("ALL DONE ->", OUT)

if __name__ == "__main__":
    main()
