# -*- coding: utf-8 -*-
import json
r = json.load(open("D:/hermes/analysis/_b1012_news2.json", encoding="utf-8"))
for k in ["nature","science","cidrap","hn"]:
    print(f"===== {k} =====")
    for it in r[k][:22]:
        if isinstance(it, dict):
            print(" •", it.get("title","")[:120], "|", it.get("desc","")[:140])
        else:
            print(" •", str(it)[:120])
    print()
for k, v in r["bing"].items():
    print(f"===== bing:{k} =====")
    for it in v:
        print(" •", it.get("title","")[:110], "||", it.get("desc","")[:160])
    print()
