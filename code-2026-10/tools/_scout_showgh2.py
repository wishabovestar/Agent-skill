import json, os
base = r"D:/hermes/data/intel"
d = json.load(open(os.path.join(base, "logs", "_new_20260918.json"), encoding="utf-8"))
lines = []
for k, items in d["gh_new"].items():
    if not items:
        continue
    lines.append(f"=== {k} ({len(items)}) ===")
    for i in items[:12]:
        lines.append(f"  {i['full_name']} | {i['stars']} | {i.get('lang')} | c{i.get('created')} p{i.get('pushed')}")
        lines.append(f"     {(i.get('desc') or '')[:100]}")
open(r"D:/hermes/analysis/_ghview.txt", "w", encoding="utf-8").write("\n".join(lines))
print("lines:", len(lines))
