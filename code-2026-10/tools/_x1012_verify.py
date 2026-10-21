# -*- coding: utf-8 -*-
import json, ssl, urllib.request, time
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

def get(url, tries=3):
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
                return json.loads(r.read().decode("utf-8", "ignore"))
        except Exception as e:
            last = f"{type(e).__name__}:{str(e)[:60]}"; time.sleep(3)
    return {"__err__": last}

CANDS = ["slopus/happy","danyuchn/asd-ste100-skill","NousResearch/hermes-official-plugins",
         "bherbruck/solidcraft","sno-ai/sno-station-skills","AI-BizOS/cross-harness",
         "lawrencewzen/wx-bot","Atoll92/agent-standup","VITASID57/dudulove-memory",
         "VecSzn/PolyStrata","LingCore/WinShun","mattpocock/skills","Panniantong/Agent-Reach",
         "paperclipai/paperclip","JustVugg/colibri","TencentCloud/Octop","trycua/cua","NVIDIA/OpenShell"]

res = []
for nm in CANDS:
    d = get("https://api.github.com/repos/" + nm)
    if "__err__" in d:
        print("ERR", nm, d["__err__"]); res.append({"full": nm, "err": d["__err__"]}); continue
    rec = {"full": d.get("full_name"), "stars": d.get("stargazers_count"), "forks": d.get("forks_count"),
           "lang": d.get("language"), "created": d.get("created_at"), "pushed": d.get("pushed_at"),
           "size": d.get("size"), "license": (d.get("license") or {}).get("spdx_id"),
           "topics": d.get("topics", []), "homepage": d.get("homepage"),
           "open_issues": d.get("open_issues_count"), "desc": (d.get("description") or "")[:200]}
    res.append(rec)
    shell = "SHELL?" if (rec["size"] and rec["size"] < 5 and rec["forks"] == 0 and not rec["license"] and not rec["homepage"]) else "ok"
    print("%-42s *%-7s %-12s f=%-5s sz=%-6s %s | %s" % (nm, rec["stars"], rec["lang"], rec["forks"], rec["size"], shell, (rec["desc"] or "")[:60]))
    time.sleep(1)

json.dump(res, open("D:/hermes/analysis/x1012_verified.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("VERIFIED", len(res))
