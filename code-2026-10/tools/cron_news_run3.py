#!/usr/bin/env python3
"""Round-3 Bing queries: battery papers + fill gaps."""
import re, html, urllib.request, urllib.parse, datetime, xml.etree.ElementTree as ET, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp", "news_results3.txt")

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
            if any(k in title for k in ["_百度百科", "汉典", "汉语", "是什么意思", "笔顺"]):
                continue
            if title and link:
                results.append((title, link, desc[:220], pub))
    except Exception as e:
        results.append(("QUERY_ERROR", str(e), query, ""))
    return results

QUERIES = {
    "BATPAPER": [
        "固态电池 研究 论文 最新 Nature 2026",
        "锂电池 硅碳负极 论文 最新 2026",
        "锂硫电池 锂空气电池 研究进展 2026",
    ],
    "TECHFILL": [
        "特斯拉 芯片厂 得州 Terafab",
        "磷酸铁锂 价格 8月 2026",
        "动力电池 装车量 7月 2026",
        "储能 政策 发改委 2026年8月",
    ],
    "AIFILL": [
        "AI Agent 框架 开源 最新 2026年8月",
        "大模型 融资 创业 公司 2026年8月",
    ],
    "VIRUSFILL": [
        "新冠疫情 中疾控 7月 通报",
        "流感 监测 2026 第29周",
    ],
}

def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("=== NEWS DUMP R3 %s ===\n" % datetime.datetime.now().isoformat())
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
