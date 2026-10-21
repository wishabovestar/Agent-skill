# -*- coding: utf-8 -*-
"""Parse v2: fix RDF, CIDRAP h2/h3, HN resolve, Bing CN searches."""
import json, re, html, urllib.request, urllib.parse, ssl, time, os
d = json.load(open("D:/hermes/analysis/_b1012_news_raw.json", encoding="utf-8"))
res = json.load(open("D:/hermes/analysis/_b1012_news.json", encoding="utf-8"))
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
PROXY = "socks5h://127.0.0.1:10808"

def clean(s):
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s or "", flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s); s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()

def parse_rdf(xml, n=25):
    out = []
    for m in re.finditer(r"<item(?:\s[^>]*)?>(.*?)</item>", xml, re.S):
        b = m.group(1)
        t = re.search(r"<title[^>]*>(.*?)</title>", b, re.S)
        l = re.search(r"<link[^>]*>(.*?)</link>", b, re.S)
        de = re.search(r"<description[^>]*>(.*?)</description>", b, re.S)
        if not l:
            lm = re.search(r'rdf:about="([^"]+)"', m.group(0))
            l = lm if lm else None
        title = clean(t.group(1) if t else "")
        if title:
            out.append({"title": title, "link": clean(l.group(1) if l else ""),
                        "desc": clean(de.group(1) if de else "")[:280]})
        if len(out) >= n: break
    return out

res["nature"] = parse_rdf(d.get("nature",""))
res["science"] = parse_rdf(d.get("science",""))

# CIDRAP h2/h3
cd = d.get("cidrap","")
cd_items = []
skip = {"Main navigation","News Briefs","Ebola","In case you missed it","Osterholm Update Podcast"}
for m in re.finditer(r"<(h2|h3)[^>]*>(.*?)</\1>", cd, re.S):
    t = clean(m.group(2))
    if t and t not in skip and 8 < len(t) < 160:
        cd_items.append(t)
res["cidrap"] = list(dict.fromkeys(cd_items))[:30]

# HN resolve
hn_ids = json.loads(d.get("hn","[]"))[:18] if d.get("hn","").startswith("[") else []
hn_items = []
op = urllib.request.build_opener(urllib.request.ProxyHandler({"http":PROXY,"https":PROXY}))
for i in hn_ids:
    try:
        u = f"https://hacker-news.firebaseio.com/v0/item/{i}.json"
        j = json.loads(op.open(urllib.request.Request(u, headers={"User-Agent":UA}), timeout=15).read().decode())
        if j and j.get("type")=="story":
            hn_items.append({"title": j.get("title",""), "score": j.get("score",0),
                             "url": j.get("url") or f"https://news.ycombinator.com/item?id={i}",
                             "descendants": j.get("descendants",0)})
    except Exception as e:
        pass
res["hn"] = hn_items

# Bing CN searches (direct, 80-port style)
def bing(q, n=12):
    url = "http://cn.bing.com/search?q=" + urllib.parse.quote(q) + f"&count={n}&setlang=zh-CN"
    for att in range(2):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent":UA,"Accept-Language":"zh-CN,zh;q=0.9"}), timeout=20)
            h = r.read().decode("utf-8","ignore")
            out = []
            for m in re.finditer(r'<li class="b_algo".*?<h2[^>]*>(.*?)</h2>.*?<p[^>]*>(.*?)</p>', h, re.S):
                t = clean(m.group(1)); de = clean(m.group(2))
                if t: out.append({"title": t, "desc": de[:220]})
                if len(out) >= n: break
            if not out:
                for m in re.finditer(r'<h2[^>]*>(.*?)</h2>', h, re.S):
                    t = clean(m.group(1))
                    if t and len(t) > 5: out.append({"title": t, "desc": ""})
            return out
        except Exception as e:
            if att == 1: return [{"ERR": str(e)[:80]}]
            time.sleep(2)

SEARCHES = {
    "virus_cn": "新冠 流感 变异株 2026年10月 疫情",
    "virus_en": "COVID-19 new variant influenza October 2026",
    "li_price": "碳酸锂 价格 10月12日",
    "li_tech": "固态电池 硅碳负极 最新进展 2026",
    "tech_fin": "英伟达 台积电 财报 半导体 2026年10月",
}
res["bing"] = {}
for k, q in SEARCHES.items():
    res["bing"][k] = bing(q)
    print(f"bing {k}: {len(res['bing'][k])}")

json.dump(res, open("D:/hermes/analysis/_b1012_news2.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED. cidrap:",len(res["cidrap"]),"nature:",len(res["nature"]),"science:",len(res["science"]),"hn:",len(res["hn"]))
