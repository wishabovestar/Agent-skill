import json, os
base = r"D:/hermes/data/intel"
d = json.load(open(os.path.join(base, "logs", "_new_20260918.json"), encoding="utf-8"))
for k, items in d["gh_new"].items():
    if not items:
        continue
    print(f"=== {k} ({len(items)}) ===")
    for i in items[:12]:
        print(f"  {i['full_name']} | {i['stars']} | {i.get('lang')} | c{i.get('created')} p{i.get('pushed')}")
        print(f"     {(i.get('desc') or '')[:110]}")
