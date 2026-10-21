# -*- coding: utf-8 -*-
import ssl, urllib.request, json, time, os, glob, re
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

def repo_info(full):
    url = "https://api.github.com/repos/" + full
    for k in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
                d = json.loads(r.read().decode("utf-8", "ignore"))
            return {"full": full, "stars": d.get("stargazers_count"), "forks": d.get("forks_count"),
                    "created": (d.get("created_at") or "")[:10], "lang": d.get("language"),
                    "topics": d.get("topics", [])[:8], "desc": (d.get("description") or "")[:130],
                    "size": d.get("size"), "license": (d.get("license") or {}).get("spdx_id"),
                    "url": d.get("html_url")}
        except Exception as e:
            if k == 2:
                return {"full": full, "err": f"{type(e).__name__}:{str(e)[:50]}"}
            time.sleep(3)

TARGETS = ["mattpocock/skills", "affaan-m/ECC", "multica-ai/andrej-karpathy-skills",
           "DietrichGebert/ponytail", "morluto/rea", "vectorize-io/hindsight",
           "paperclipai/paperclip", "thedotmack/claude-mem", "addyosmani/agent-skills",
           "heygen-com/hyperframes", "cathrynlavery/diagram-design"]

# quick seen build (same rules)
seen = set()
for root in ["D:/hermes/data/agent_knowledge", "D:/hermes/data/math_knowledge",
             "D:/hermes/data/book_knowledge", "D:/hermes/data/physics_knowledge", "D:/hermes/data/intel"]:
    for f in glob.glob(root + "/**/*.json", recursive=True):
        fp = f.replace("\\", "/")
        if "/tmp/" in fp or os.path.basename(fp).startswith("_") or "2026-10-11" in fp:
            continue
        try: d = json.load(open(f, encoding="utf-8", errors="ignore"))
        except Exception: continue
        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in ("full_name", "repo", "name") and isinstance(v, str) and "/" in v:
                        seen.add(v.split("github.com/")[-1].strip("/").lower())
                    walk(v)
            elif isinstance(o, list):
                for v in o: walk(v)
        walk(d)

res = []
for t in TARGETS:
    info = repo_info(t)
    info["is_new"] = t.lower() not in seen
    res.append(info)
    print("%-42s *%-8s %s new=%s %s" % (info.get("full", t), info.get("stars", info.get("err")),
          info.get("created", ""), info.get("is_new", "?"), (info.get("desc") or "")[:60]))
    time.sleep(2)

json.dump(res, open("D:/hermes/analysis/x1011_verified.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED", len(res))
