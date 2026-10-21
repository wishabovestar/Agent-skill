#!/usr/bin/env python3
"""Round-2 Bing queries with improved phrasing. Appends to tmp/news_results2.txt"""
import re, html, urllib.request, urllib.parse, datetime, xml.etree.ElementTree as ET, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp", "news_results2.txt")

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
            # filter out dictionary/baike noise
            if any(k in title for k in ["_百度百科", "汉典", "汉语", "是什么意思"]):
                continue
            if title and link:
                results.append((title, link, desc[:220], pub))
    except Exception as e:
        results.append(("QUERY_ERROR", str(e), query, ""))
    return results

QUERIES = {
    "VIRUS2": [
        "禽流感 H5N1 最新消息 2026",
        "猴痘 mpox 世卫组织 最新",
        "世卫组织 新冠 声明 8月",
    ],
    "AI2": [
        "OpenAI GPT 发布 最新消息",
        "DeepSeek 新模型 发布 2026",
        "国产大模型 发布 8月",
    ],
    "BATTERY2": [
        "全固态电池 量产 最新进展",
        "固态电池 装车 车企 2026",
        "锂矿 价格 停产 2026年8月",
        "宁德时代 比亚迪 电池 最新",
    ],
    "PAPERS2": [
        "arxiv 最新论文 AI 2026年8月",
        "arXivDaily 今日 论文",
        "site:arxivdaily.com",
    ],
    "TECHFIN2": [
        "英伟达 财报 2026",
        "台积电 芯片 最新 2026年8月",
        "芯片 出口管制 美国 2026",
        "光伏 储能 政策 2026年8月",
    ],
}

def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("=== NEWS DUMP R2 %s ===\n" % datetime.datetime.now().isoformat())
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
