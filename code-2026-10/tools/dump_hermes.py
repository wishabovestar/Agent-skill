import json
new = json.load(open("D:/hermes/analysis/new_all.json", encoding="utf-8"))
trending = json.load(open("D:/hermes/analysis/trending_parsed.json", encoding="utf-8"))

print("=== NEW repos with hermes/mcp/agent-skill in topics or desc ===")
for x in new:
    blob = (x["full_name"] + " " + x["desc"] + " " + " ".join(x["topics"] or [])).lower()
    if "hermes" in blob or "mcp" in blob or "agent-skill" in blob or "agent skill" in blob:
        print(f"★{x['stars']:>5} {x['full_name'][:44]:44} | {x['desc'][:70]}")

print("\n=== TRENDING (47) ===")
for t in sorted(trending, key=lambda z: -(z.get("stars") or 0)):
    print(f"★{t.get('stars'):>7} {t['repo'][:44]:44} gain{t.get('period_gain')} | {t['desc'][:58]}")
