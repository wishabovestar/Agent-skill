import json
final = json.load(open(r"D:/hermes/data/intel/logs/_final_20260918.json", encoding="utf-8"))
for t in (1, 2, 3):
    print(f"### T{t}")
    for c in final:
        if c["t"] == t:
            print(f"{c['title']} || {c['url']} || {c['d']}")
