import re, html

raw = open("D:/hermes/analysis/trending_raw.html", encoding="utf-8", errors="ignore").read()
parts = re.split(r"===XX:(\w+)===XX", raw)
periods = {}
for i in range(1, len(parts) - 1, 2):
    periods[parts[i]] = parts[i + 1]

body = periods["daily"]
idxs = [m.start() for m in re.finditer(r'<h2 class="h3 lh-condensed">', body)]
print("num cards daily:", len(idxs))
for n in range(2):
    p = idxs[n]
    block = body[p: idxs[n + 1] if n + 1 < len(idxs) else p + 6000]
    t = re.sub(r"<[^>]+>", " ", block)
    t = re.sub(r"\s+", " ", t)
    print(f"--- card {n} text (len {len(t)}) ---")
    print(t[:600])
    print()
