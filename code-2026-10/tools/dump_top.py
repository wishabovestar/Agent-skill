import json
new = json.load(open("D:/hermes/analysis/new_all.json", encoding="utf-8"))
for n, x in enumerate(new[:26], 1):
    t = ",".join((x.get("topics") or [])[:6])
    print(f"{n}|{x['full_name']}|★{x['stars']}|{x['lang']}|score={x['score']}|created={(x['created'] or '')[:10]}|src={x['src'][:22]}")
    print(f"   T:{t[:90]}")
    print(f"   D:{x['desc'][:150]}")
