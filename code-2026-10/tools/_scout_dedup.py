import json, os

base = r"D:/hermes/data/intel"
seen = json.load(open(os.path.join(base, "logs", "_seen_cache.json"), encoding="utf-8"))["urls"]
seenset = set(seen)

cand = json.load(open(os.path.join(base, "logs", "_cand_20260918.json"), encoding="utf-8"))

def norm(u):
    return u.strip().rstrip("/").lower()

new = []
dup = 0
for c in cand:
    if norm(c["url"]) in seenset:
        dup += 1
        continue
    new.append(c)
print("WEB cand:", len(cand), "dup:", dup, "NEW:", len(new))

# GitHub results
gh = json.load(open(os.path.join(base, "logs", "_gh_raw_20260918.json"), encoding="utf-8"))
gh_new = {}
for k, v in gh.items():
    if not isinstance(v, list):
        continue
    items = [i for i in v if norm(i["url"]) not in seenset and norm("https://github.com/" + i["full_name"]) not in seenset]
    gh_new[k] = items
    print(f"GH [{k}] {len(v)} -> new {len(items)}")

json.dump({"web_new": new, "gh_new": gh_new},
          open(os.path.join(base, "logs", "_new_20260918.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("---- WEB NEW LIST ----")
for c in new:
    print(f"T{c['t']}|{c['title'][:70]}|{c['url'][:70]}")
