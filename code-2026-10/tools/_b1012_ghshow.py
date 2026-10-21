# -*- coding: utf-8 -*-
import json
v=json.load(open("D:/hermes/analysis/x1012_verified.json",encoding="utf-8")) if True else []
print("count:",len(v))
for it in v:
    print(f"{it['full']} | ⭐{it['stars']} | {it.get('lang')} | {it.get('created','')[:10]} | {(it.get('desc') or '')[:110]}")
print("--- buckets ---")
try:
    b=json.load(open("D:/hermes/analysis/gh_buckets_1012.json",encoding="utf-8"))
    print(type(b), list(b.keys())[:20] if isinstance(b,dict) else len(b))
except Exception as e:
    print("buckets err",e)
