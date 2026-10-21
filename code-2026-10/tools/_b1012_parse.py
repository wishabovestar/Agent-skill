# -*- coding: utf-8 -*-
"""Parse news raw -> structured headlines."""
import json, re, html
d = json.load(open("D:/hermes/analysis/_b1012_news_raw.json", encoding="utf-8"))
res = {}

def clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()

def parse_rss(xml, n=25):
    out = []
    for m in re.finditer(r"<item[^>]*>(.*?)</item>", xml, re.S):
        b = m.group(1)
        t = re.search(r"<title[^>]*>(.*?)</title>", b, re.S)
        l = re.search(r"<link[^>]*>(.*?)</link>", b, re.S)
        de = re.search(r"<description[^>]*>(.*?)</description>", b, re.S)
        dt = re.search(r"<pubDate[^>]*>(.*?)</pubDate>", b, re.S)
        out.append({"title": clean(t.group(1) if t else ""), "link": clean(l.group(1) if l else ""),
                    "desc": clean(de.group(1) if de else "")[:300], "date": clean(dt.group(1) if dt else "")})
        if len(out) >= n: break
    return out

res["ithome"] = parse_rss(d.get("ithome",""))
res["cnbeta"] = parse_rss(d.get("cnbeta",""))
res["cidrap"] = parse_rss(d.get("cidrap",""))
res["nature"] = parse_rss(d.get("nature",""))
res["science"] = parse_rss(d.get("science",""))
res["arstech"] = parse_rss(d.get("arstech",""))

# ECDC: extract headline links
ec = d.get("ecdc","")
ec_items = []
for m in re.finditer(r'<a href="(/en/[^"]+)"[^>]*>([^<]{15,140})</a>', ec):
    href, txt = m.group(1), clean(m.group(2))
    if any(w in txt.lower() for w in ["outbreak","threat","week","influenza","covid","measles","mpox","dengue","chikungunya","avian","respiratory","surveillance","salmonella","legionella"]):
        ec_items.append({"title": txt, "link": "https://www.ecdc.europa.eu"+href})
res["ecdc"] = ec_items[:20]

# sina tech json
st = d.get("sina_tech","")
sj = []
try:
    j = json.loads(st)
    for it in j["result"]["data"]:
        sj.append({"title": it.get("title",""), "url": it.get("url",""), "media": it.get("media_name",""),
                   "time": it.get("ctime","")})
except Exception as e:
    sj = [{"ERR": str(e)[:60]}]
res["sina_tech"] = sj[:30]

# nbd headlines
nb = d.get("nbd","")
nb_items = []
for m in re.finditer(r'<a[^>]+href="(https?://[^"]*nbd\.com\.cn[^"]*)"[^>]*>([^<]{12,90})</a>', nb):
    nb_items.append({"title": clean(m.group(2)), "link": m.group(1)})
res["nbd"] = nb_items[:30]

# smm: find 碳酸锂 / 锂 mentions
smm = d.get("smm","")
smm_items = []
for m in re.finditer(r'>([^<>]*锂[^<>]{2,60})<', smm):
    t = clean(m.group(1))
    if len(t) > 4: smm_items.append(t)
res["smm_li"] = list(dict.fromkeys(smm_items))[:40]

# thepaper headlines
tp = d.get("thepaper","")
tp_items = []
for m in re.finditer(r'"name":"([^"]{10,80})"[^}]*?"nodeInfo":\{"node_id":"(\d+)"', tp):
    tp_items.append(m.group(1))
if not tp_items:
    for m in re.finditer(r'<a[^>]+href="(/newsDetail_[^"]+|/detail[^"]*)"[^>]*>([^<]{8,80})</a>', tp):
        tp_items.append(clean(m.group(2)))
res["thepaper"] = tp_items[:30]

json.dump(res, open("D:/hermes/analysis/_b1012_news.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
for k,v in res.items():
    print(f"--- {k}: {len(v)}")
print("SAVED")
