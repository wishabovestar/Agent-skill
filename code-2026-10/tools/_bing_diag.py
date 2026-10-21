# -*- coding: utf-8 -*-
"""诊断 Bing News RSS 返回体"""
import ssl, sys, io, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=CTX))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
url = "https://cn.bing.com/news/search?q=%E9%94%82%E7%94%B5&format=rss"
with OPENER.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=25) as r:
    b = r.read()
    print("status", r.status, "ctype", r.headers.get("Content-Type"), "enc", r.headers.get("Content-Encoding"), "len", len(b))
print("HEAD:", repr(b[:300]))
try:
    t = b.decode("utf-8-sig", "ignore")
    print("DECODED_HEAD:", repr(t[:300]))
    print("HAS_ITEM:", "<item" in t, "COUNT:", t.count("<item>"))
except Exception as e:
    print("DEC_ERR", e)
open("D:/hermes/analysis/_bing_news_raw.txt", "wb").write(b)
