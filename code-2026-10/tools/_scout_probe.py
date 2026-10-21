import json, os, glob

base = r"D:/hermes/data/intel"
print("== dirs under intel ==")
for d in sorted(os.listdir(base)):
    p = os.path.join(base, d)
    if os.path.isdir(p):
        n = len(os.listdir(p))
        print(f"  {d}/ ({n} files)")

log = os.path.join(base, "logs", "collection_log.json")
print("\n== collection_log.json ==")
if os.path.exists(log):
    print("size:", os.path.getsize(log))
    try:
        data = json.load(open(log, encoding="utf-8"))
        if isinstance(data, dict):
            print("keys:", list(data.keys())[:20])
            for k, v in list(data.items())[:5]:
                print(" ", k, "->", str(v)[:200])
        elif isinstance(data, list):
            print("list len:", len(data))
            for it in data[-5:]:
                print("  ", json.dumps(it, ensure_ascii=False)[:250])
    except Exception as e:
        print("parse err:", e)
else:
    print("NOT FOUND")

for sub in ["tata_apple", "anthropic_code"]:
    p = os.path.join(base, sub)
    print(f"\n== {sub} ==")
    if os.path.isdir(p):
        for f in sorted(os.listdir(p))[-12:]:
            print("  ", f, os.path.getsize(os.path.join(p, f)))
    else:
        print("  NOT FOUND")
