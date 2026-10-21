# -*- coding: utf-8 -*-
"""Lithium price + China CDC + WHO alt sources."""
import urllib.request, urllib.parse, ssl, json, re, html, time, os
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
PROXY = "socks5h://127.0.0.1:10808"
def clean(s):
    s = re.sub(r"<[^>]+>", " ", s or ""); s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()
def fetch(url, proxy=False, timeout=25, enc="utf-8"):
    req = urllib.request.Request(url, headers={"User-Agent":UA,"Accept-Language":"zh-CN,zh;q=0.9"})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({"http":PROXY,"https":PROXY})) if proxy else urllib.request.build_opener()
    r = op.open(req, timeout=timeout); raw = r.read()
    try: return raw.decode(enc,"ignore")
    except: return raw.decode("gbk","ignore")
def tf(url, **kw):
    for a in range(2):
        try: return fetch(url, **kw)
        except Exception as e:
            if a==1: return "__ERR__ "+str(e)[:90]
            time.sleep(2)

OUT = {}
# lithium price sources
OUT["smm_price"] = tf("https://www.smm.cn/new-energy/category/1", timeout=25)
OUT["smm_li_news"] = tf("https://news.smm.cn/", timeout=25)
OUT["100ppi"] = tf("https://www.100ppi.com/mprice/detail-2.html", timeout=20)
OUT["ccmn"] = tf("https://www.ccmn.cn/", timeout=20)
OUT["mysteel"] = tf("https://www.mysteel.com/", timeout=20)
OUT["chinacdc"] = tf("https://www.chinacdc.cn/", timeout=20)
OUT["chinacdc_covid"] = tf("https://www.chinacdc.cn/jkzt/crb/zl/szkb_11803/", timeout=20)
OUT["ecdc_cdtr"] = tf("https://www.ecdc.europa.eu/en/publications-data/communicable-disease-threats-report-4-10-october-2026", proxy=True, timeout=25)
OUT["who_covid_ct"] = tf("https://data.who.int/dashboards/covid19/cases", proxy=True, timeout=25)
for k,v in OUT.items():
    print(k, "ERR" if (isinstance(v,str) and v.startswith("__ERR__")) else f"OK {len(v)}")
json.dump(OUT, open("D:/hermes/analysis/_b1012_li.json","w",encoding="utf-8"), ensure_ascii=False)
print("SAVED")
