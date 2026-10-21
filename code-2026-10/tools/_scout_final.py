# -*- coding: utf-8 -*-
import json, os, sys
sys.path.insert(0, r"D:/hermes/data/intel/logs")
from _extra_20260918 import EXTRA

base = r"D:/hermes/data/intel"
seen = set(json.load(open(os.path.join(base, "logs", "_seen_cache.json"), encoding="utf-8"))["urls"])
newdata = json.load(open(os.path.join(base, "logs", "_new_20260918.json"), encoding="utf-8"))

def norm(u):
    return u.strip().rstrip("/").lower()

allc = newdata["web_new"] + EXTRA
# dedupe within set too
seen_now = set(seen)
final = []
for c in allc:
    n = norm(c["url"])
    if n in seen_now:
        continue
    seen_now.add(n)
    final.append(c)

by = {1: [], 2: [], 3: []}
for c in final:
    by[c["t"]].append(c)

for t in (1, 2, 3):
    print(f"T{t}: {len(by[t])}")
json.dump(final, open(os.path.join(base, "logs", "_final_20260918.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
