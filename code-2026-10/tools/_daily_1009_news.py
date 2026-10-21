#!/usr/bin/env python3
import re, html, urllib.request, urllib.parse, json, os, xml.etree.ElementTree as ET, time

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_daily_1009_news.json")
PROXY = "http://127.0.0.1:8899"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http":PROXY,"https":PROXY}))

def search(query, num=6):
    url = "https://cn.bing.com/search?q=" + urllib.parse.quote(query) + "&format=rss&count=%d&setlang=zh-CN" % num
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    })
    results = []
    try:
        with opener.open(req, timeout=25) as r:
            data = r.read().decode("utf-8", "ignore")
        root = ET.fromstring(data)
        for it in root.findall(".//item")[:num]:
            def g(tag, attr=None):
                e = it.find(tag)
                if e is None: return ""
                return e.get(attr, "") or "" if attr else (e.text or "").strip()
            title = html.unescape(g("title"))
            link = g("link", "href") or g("link")
            desc = re.sub(r"<[^>]+>", " ", g("description"))
            desc = html.unescape(re.sub(r"\s+", " ", desc)).strip()
            pub = g("pubDate")
            bad = ["_百度百科","汉典","汉语","是什么意思","笔顺","翻译","词典"]
            if any(k in title for k in bad): continue
            if title and link: results.append({"t":title,"u":link,"d":desc[:260],"pub":pub})
    except Exception as e:
        results.append({"t":"QUERY_ERROR","u":str(e),"d":query,"pub":""})
    return results

QUERIES = {
 "VIRUS_NEW": ["COVID-19 new variant 2026 October", "influenza H5N1 avian flu update October 2026", "WHO ECDC COVID variant report 2026", "流感 新冠 变异株 2026年10月"],
 "BATTERY_NEWS": ["碳酸锂 价格 2026年10月", "固态电池 量产 装车 2026", "硅碳负极 产业化 2026", "锂电池 行业 动态 2026年10月"],
 "TECH_FIN": ["英伟达 财报 AI 芯片 2026", "半导体 出口管制 2026", "新能源 政策 补贴 2026年10月", "科技巨头 财报 2026"],
}
res={}
for k,qs in QUERIES.items():
    print("###", k)
    res[k]=[]
    for q in qs:
        got = search(q)
        res[k].append({"q":q,"items":got})
        for it in got:
            print(" -", it["t"][:110])
            print("   ", it["u"][:120])
        time.sleep(1)
    print()
json.dump(res, open(OUT,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("saved", OUT)
