# -*- coding: utf-8 -*-
import json, re, html
d = json.load(open("D:/hermes/analysis/_b1012_li.json", encoding="utf-8"))
def clean(s):
    s = re.sub(r"<[^>]+>"," ",s or ""); s=html.unescape(s)
    return re.sub(r"\s+"," ",s).strip()
for k in ["smm_li_news","ccmn","mysteel","100ppi","chinacdc","who_covid_ct"]:
    v = d.get(k,"")
    print(f"===== {k} ({len(v)}) =====")
    print(clean(v)[:900])
    print()
# search 碳酸锂 mentions
for k in ["smm_li_news","ccmn","mysteel","chinacdc","who_covid_ct"]:
    v = d.get(k,"")
    txt = clean(v)
    hits = []
    for kw in ["碳酸锂","氢氧化锂","锂盐","锂价","电碳"]:
        for m in re.finditer(kw+r"[^。；\s]{0,40}", txt):
            hits.append(m.group(0))
    if hits:
        print(f"--- {k} 锂相关 ---")
        print(" | ".join(list(dict.fromkeys(hits))[:12]))
