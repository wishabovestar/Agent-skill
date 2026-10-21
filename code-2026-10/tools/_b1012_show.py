# -*- coding: utf-8 -*-
import json
d = json.load(open("D:/hermes/analysis/_b1012_news.json", encoding="utf-8"))
for k in ["ithome","cnbeta","nature","science","arstech","ecdc"]:
    print(f"===== {k} =====")
    for it in d[k][:25]:
        print(" •", it["title"][:110], "|", it.get("link","")[:70])
    print()
print("===== sina_tech =====")
for it in d["sina_tech"][:25]:
    print(" •", it.get("title","")[:100])
print("\n===== nbd =====")
for it in d["nbd"][:25]:
    print(" •", it["title"][:100])
print("\n===== smm_li =====")
print(" | ".join(d["smm_li"]))
