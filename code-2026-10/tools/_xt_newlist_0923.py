import json
d=json.load(open("D:/hermes/analysis/_xt0923/merged_0923.json",encoding="utf-8"))
new=sorted(d["new"],key=lambda x:(-x["relevance"],-x["stars"]))
print(f"NEW_TOTAL={len(new)}")
for i,it in enumerate(new,1):
    print(f"{i}|{it['full_name']}|{it['stars']}|rel{it['relevance']}|{it['language']}|{it['created_at']}|{(it['description'] or '')[:72]}")
