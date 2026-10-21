# -*- coding: utf-8 -*-
import json, re
d = json.load(open("D:/hermes/analysis/_b1012_news_raw.json", encoding="utf-8"))
for k in ["ecdc","cidrap","nature","science","arstech","thepaper","36kr","ithome","cnbeta","sina_tech","smm","nbd"]:
    v = d.get(k,"")
    print(f"===== {k} ({len(v)}) =====")
    print(v[:600].replace("\n"," "))
    print()
