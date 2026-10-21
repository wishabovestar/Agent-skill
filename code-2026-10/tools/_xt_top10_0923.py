import json
d=json.load(open("D:/hermes/analysis/_xt0923/merged_0923.json",encoding="utf-8"))
top=sorted([x for x in d["top"] if x["relevance"]>=6],key=lambda x:(-x["relevance"],not x["is_new"],-x["stars"]))[:10]
for i,it in enumerate(top,1):
    print(f"{i}|{it['full_name']}|{it['stars']}|rel{it['relevance']}|new={it['is_new']}|{it['language']}|{it['created_at']}|push{it['pushed_at']}|{it['license']}")
    print(f"   {(it['description'] or '')[:230]}")
