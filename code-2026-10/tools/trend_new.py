import json
new = json.load(open("D:/hermes/analysis/new_all.json", encoding="utf-8"))
trending = json.load(open("D:/hermes/analysis/trending_parsed.json", encoding="utf-8"))
newkeys = {x["full_name"].lower() for x in new}
print("=== TRENDING items that are NEW (not in seen) ===")
for t in trending:
    if t["repo"].lower() in newkeys:
        print(f"★{t.get('stars')} {t['repo']} gain{t.get('period_gain')} | {t['desc'][:70]}")
print("count:", sum(1 for t in trending if t["repo"].lower() in newkeys))
