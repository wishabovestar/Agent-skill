# -*- coding: utf-8 -*-
import json, re
d = json.load(open("D:/hermes/analysis/_b1012_news_raw.json", encoding="utf-8"))
for k in ["nature","science"]:
    v = d[k]
    i = v.find("<item")
    print(f"===== {k} item snippet =====")
    print(v[i:i+500])
    print()
v = d["cidrap"]
print("===== cidrap structure =====")
for m in re.finditer(r'<article[^>]*>', v):
    print(m.group(0)[:200])
print("--- cidrap h2/h3 ---")
for m in re.finditer(r'<(h2|h3)[^>]*>(.*?)</\1>', v, re.S):
    print(re.sub(r"\s+"," ",re.sub(r"<[^>]+>","",m.group(2)))[:120])
print("--- cidrap views-row titles ---")
for m in re.finditer(r'class="[^"]*title[^"]*"[^>]*>.*?</a>', v, re.S)[:0] if False else []:
    pass
print(len(re.findall(r'<a[^>]+href="(/news/[^"]+)"', v)), "news links")
