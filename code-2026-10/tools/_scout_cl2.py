import re, json
html = open(r"D:/hermes/data/intel/logs/_cl_docket_20260918.html", encoding="utf-8").read()

# find entry rows: look for 'recap-documents' anchors or 'Entry' patterns
nums = re.findall(r'id="entry-(\d+)"', html)
print("entry-id anchors:", len(nums), "max:", max(map(int, nums)) if nums else None)

pairs = re.findall(r'(\d{2,3})\s*(?:\n|\s)*\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2}),\s+(\d{4})', html)
print("pairs:", len(pairs))

# date-based scan on stripped text
txt = re.sub(r"<[^>]+>", "\n", html)
txt = re.sub(r"\n{2,}", "\n", txt)
lines = [l.strip() for l in txt.splitlines()]
idx = []
for i, l in enumerate(lines):
    if re.fullmatch(r"\d{2,3}", l) and i + 1 < len(lines):
        nxt = lines[i + 1]
        if re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.? \d{1,2}, \d{4}$", nxt):
            idx.append((int(l), nxt, " ".join(lines[i + 2:i + 5])[:110]))
print("structured rows:", len(idx))
idx.sort(key=lambda x: -x[0])
seen = set(); keep = []
for r in idx:
    if r[0] in seen: continue
    seen.add(r[0]); keep.append(r)
print("MAX ENTRY:", keep[0][0] if keep else None)
for r in keep[:14]:
    print(f"{r[0]} | {r[1]} | {r[2][:85]}")
json.dump(keep, open(r"D:/hermes/data/intel/logs/_cl_rows_20260918.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
