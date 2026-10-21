import re, json, html

raw = open("D:/hermes/analysis/trending_raw.html", encoding="utf-8", errors="ignore").read()
parts = re.split(r"===XX:(\w+)===XX", raw)
# parts: [pre, 'daily', body, 'weekly', body, 'monthly', body]
periods = {}
for i in range(1, len(parts) - 1, 2):
    periods[parts[i]] = parts[i + 1]

def parse_period(txt):
    out = []
    idxs = [m.start() for m in re.finditer(r'<h2 class="h3 lh-condensed">', txt)]
    for n, p in enumerate(idxs):
        block = txt[p: idxs[n + 1] if n + 1 < len(idxs) else p + 4000]
        m = re.search(r'href="/([^"/]+/[^"/]+)"', block)
        if not m:
            continue
        repo = m.group(1)
        desc = ""
        dm = re.search(r'<p class="col-9[^"]*"[^>]*>\s*(.*?)\s*</p>', block, re.S)
        if dm:
            desc = re.sub(r"<[^>]+>", " ", dm.group(1))
            desc = html.unescape(re.sub(r"\s+", " ", desc)).strip()
        # strip tags for star extraction
        t = re.sub(r"<[^>]+>", " ", block)
        t = re.sub(r"\s+", " ", t)
        stars, forks, today = None, None, None
        sm = re.search(r"([\d,]+)\s+([\d,]+)\s+Built by\s+([\d,]+)\s+stars\s+(today|this week|this month)", t)
        if sm:
            stars = int(sm.group(1).replace(",", ""))
            forks = int(sm.group(2).replace(",", ""))
            today = int(sm.group(3).replace(",", ""))
        out.append({"repo": repo, "desc": desc, "stars": stars, "forks": forks, "period_gain": today})
    return out

allr = {}
for per, body in periods.items():
    rs = parse_period(body)
    print(f"{per}: {len(rs)} cards")
    for r in rs:
        k = r["repo"].lower()
        if k not in allr:
            r["period"] = per
            allr[k] = r

print("UNIQUE_TRENDING=%d" % len(allr))
json.dump(list(allr.values()), open("D:/hermes/analysis/trending_parsed.json", "w", encoding="utf-8"), ensure_ascii=False)
# print first few with stars
for k, r in list(allr.items())[:8]:
    print(f"  {r['repo']}|★{r['stars']}|gain{r['period_gain']}|{r['desc'][:60]}")
