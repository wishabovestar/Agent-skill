import json
d=json.load(open("D:/hermes/analysis/_xt0923/pool_0923.json",encoding="utf-8"))
pool=d["pool"]
print("=== NEW POOL (13) ===")
for it in sorted(pool,key=lambda x:-x["stars"])[:13]:
    print(f"{it['full_name']}|{it['stars']}|{it['language']}|{','.join(it['source'])[:40]}|{(it['description'] or '')[:110]}")
print("=== TRENDING WEEKLY ===")
for it in sorted(d["trending"],key=lambda x:-x["period_gain"]):
    print(f"{it['period']}|{it['full_name']}|T{it['stars']}|+{it['period_gain']}|{it['language']}|{(it['description'] or '')[:90]}")
