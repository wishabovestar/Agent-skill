import json, os, re, glob

base = r"D:/hermes/data/intel"
seen_urls = set()
seen_titles = set()

# 1) from collection_log.json entries
log = os.path.join(base, "logs", "collection_log.json")
data = json.load(open(log, encoding="utf-8"))
entries = data.get("entries", [])
print("log entries:", len(entries), "collections:", len(data.get("collections", [])))

def harvest(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("url", "link", "source_url") and isinstance(v, str):
                seen_urls.add(v.strip().rstrip("/").lower())
            if k in ("title", "name") and isinstance(v, str):
                seen_titles.add(v.strip().lower()[:80])
            harvest(v)
    elif isinstance(obj, list):
        for v in obj:
            harvest(v)

harvest(entries)
harvest(data.get("collections", []))

# 2) from md files (URLs inside)
for sub in ["tata_apple", "anthropic_code", "ai_frontier"]:
    for f in glob.glob(os.path.join(base, sub, "*.md")):
        try:
            t = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for m in re.findall(r'https?://[^\s\)\]\>"\']+', t):
            seen_urls.add(m.strip().rstrip("/.,").lower())

print("seen_urls:", len(seen_urls))
print("seen_titles:", len(seen_titles))
json.dump({"urls": sorted(seen_urls), "titles": sorted(seen_titles)},
          open(r"D:/hermes/data/intel/logs/_seen_cache.json", "w", encoding="utf-8"),
          ensure_ascii=False)
print("cache saved")

# sample of recent log ids
for it in entries[-5:]:
    print(" last:", it.get("id"), it.get("timestamp"), str(it.get("targets"))[:80])
