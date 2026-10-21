# -*- coding: utf-8 -*-
import re, json, os

RAW = r"D:/hermes/data/agent_knowledge/算法/tmp/trending_raw_1013.txt"
OUT = r"D:/hermes/data/agent_knowledge/算法/tmp/trending_parsed_1013.json"
html_all = open(RAW, encoding="utf-8").read()

parts = re.split(r"===XX:(\w+)===XX", html_all)
repos = {}
for i in range(1, len(parts), 2):
    per = parts[i]; html = parts[i+1]
    blocks = re.split(r'<article class="Box-row">', html)[1:]
    per_label = {"daily":"today","weekly":"this week","monthly":"this month"}.get(per, per)
    for b in blocks:
        m = re.search(r'h3 lh-condensed">\s*<a[^>]*?href="/([^"]+)"', b, re.S)
        if not m:
            m = re.search(r'<h2 class="h3 lh-condensed">\s*<a[^>]*?href="/([^"]+)"', b, re.S)
        if not m:
            continue
        repo = m.group(1).strip().strip('/')
        if repo.startswith("sponsors/") or repo.startswith("login") or "/" not in repo:
            continue
        txt = re.sub(r"<[^>]+>", " ", b)
        txt = re.sub(r"\s+", " ", txt).strip()
        md = re.search(r'<p class="col-9[^"]*"[^>]*>\s*(.*?)\s*</p>', b, re.S)
        desc = ""
        if md:
            desc = re.sub(r"<[^>]+>", " ", md.group(1))
            desc = re.sub(r"\s+", " ", desc).strip()
        ml = re.search(r'itemprop="programmingLanguage">([^<]+)</span>', b)
        lang = ml.group(1) if ml else ""
        ms = re.search(r"([\d,]+)\s+([\d,]+)\s+Built by\s+([\d,]+)\s+stars\s+(today|this week|this month)", txt)
        stars = forks = gain = 0
        if ms:
            stars = int(ms.group(1).replace(",", ""))
            forks = int(ms.group(2).replace(",", ""))
            gain = int(ms.group(3).replace(",", ""))
        rec = {"repo": repo, "stars": stars, "forks": forks, "period_gain": gain,
               "period": per_label, "lang": lang, "desc": desc[:220]}
        if repo not in repos or (rec["stars"] or 0) > (repos[repo]["stars"] or 0):
            repos[repo] = rec

out = sorted(repos.values(), key=lambda z: -(z.get("stars") or 0))
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("TOTAL unique trending:", len(out), "with_stars:", sum(1 for t in out if t["stars"]))
for t in out:
    print("%d|+%d|%s|%s|%s" % (t["stars"], t["period_gain"], t["repo"], t["lang"], (t["desc"] or "")[:80]))
