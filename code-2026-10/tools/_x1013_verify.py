# -*- coding: utf-8 -*-
import json, ssl, urllib.request, time, sys

ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

def get(url, tries=3):
    last = ""
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
                return json.loads(r.read().decode("utf-8", "ignore"))
        except Exception as e:
            last = f"{type(e).__name__}:{str(e)[:60]}"; time.sleep(3)
    return {"__err__": last}

DATE = "2026-10-13"
outdir = "D:/hermes/data/agent_knowledge/算法"
R = json.load(open(f"{outdir}/xuntian_github_scout_{DATE}.json", encoding="utf-8"))

# candidate set: top new (agent + algo) + high-gain trending
cands = []
for x in R["new_all"][:26]:
    cands.append(x["full_name"])
for t in sorted(R["trending"], key=lambda z: -(z.get("period_gain") or 0))[:14]:
    if t["repo"] not in cands:
        cands.append(t["repo"])
cands = cands[:36]

res = []
for nm in cands:
    d = get("https://api.github.com/repos/" + nm)
    if "__err__" in d:
        print("ERR", nm, d["__err__"]); res.append({"full": nm, "err": d["__err__"]}); time.sleep(1); continue
    rec = {"full": d.get("full_name"), "stars": d.get("stargazers_count"), "forks": d.get("forks_count"),
           "lang": d.get("language"), "created": d.get("created_at"), "pushed": d.get("pushed_at"),
           "size": d.get("size"), "license": (d.get("license") or {}).get("spdx_id"),
           "topics": d.get("topics", []), "homepage": d.get("homepage"),
           "open_issues": d.get("open_issues_count"), "desc": (d.get("description") or "")[:200]}
    res.append(rec)
    shell = "SHELL?" if (rec["size"] and rec["size"] < 5 and rec["forks"] == 0 and not rec["license"] and not rec["homepage"]) else "ok"
    print("%-40s *%-7s %-12s f=%-5s sz=%-6s %s | %s" % (nm, rec["stars"], rec["lang"], rec["forks"], rec["size"], shell, (rec["desc"] or "")[:55]))
    time.sleep(1.2)

json.dump(res, open("D:/hermes/analysis/x1013_verified.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("VERIFIED", len(res))
