import json
d = json.load(open(r"D:/hermes/data/intel/logs/_cl_20260918.json", encoding="utf-8"))
rows = d.get("head", [])
print("rows:", len(rows))
for r in rows[:22]:
    print(f"{r[0]} | {r[1]} | {r[2][:80]}")
