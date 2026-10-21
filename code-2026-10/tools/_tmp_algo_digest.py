# -*- coding: utf-8 -*-
import json, os, sys, glob
RAW = r"D:/hermes/data/agent_knowledge/algorithm/tmp"
gh = json.load(open(os.path.join(RAW, "github_raw.json"), encoding="utf-8"))
ax = json.load(open(os.path.join(RAW, "arxiv_raw.json"), encoding="utf-8"))

# dedupe corpus: existing archives
seen_repos, seen_papers = set(), set()
for pat in [r"D:/hermes/data/agent_knowledge/**/*.json", r"D:/hermes/data/math_knowledge/**/*.json"]:
    for f in glob.glob(pat, recursive=True):
        if os.sep + "tmp" + os.sep in f or "_tmp" in os.path.basename(f):
            continue
        try:
            txt = open(f, encoding="utf-8").read()
        except Exception:
            continue
        if '"full_name"' not in txt and "arxiv.org/abs" not in txt and '"repo"' not in txt:
            continue
        try:
            d = json.loads(txt)
        except Exception:
            continue
        def walk(o):
            if isinstance(o, dict):
                fn = o.get("full_name") or o.get("repo") or o.get("name")
                if isinstance(fn, str) and "/" in fn: seen_repos.add(fn.lower())
                u = o.get("html_url") or o.get("url") or o.get("id") or o.get("link")
                if isinstance(u, str) and "arxiv.org" in u:
                    seen_papers.add(u.rstrip("/").split("/")[-1])
                for v in o.values(): walk(v)
            elif isinstance(o, list):
                for v in o: walk(v)
        walk(d)
json.dump({"repos": sorted(seen_repos), "papers": sorted(seen_papers)},
          open(os.path.join(RAW, "seen.json"), "w", encoding="utf-8"), ensure_ascii=False)

mode = sys.argv[1] if len(sys.argv) > 1 else "all"
if mode == "gh":
    DIRS = ["algorithm", "math", "system", "dl", "ml", "neural", "hotspot"]
    for dr in DIRS:
        items = [x for x in gh if x["direction"] == dr and not x["archived"]]
        items.sort(key=lambda x: -x["stars"])
        print("##" + dr)
        for it in items[:6]:
            dup = "DUP" if it["full_name"].lower() in seen_repos else "NEW"
            print("%s|%s|%s|%s|%s|%s" % (dup, it["full_name"], it["stars"], it["language"] or "-",
                  it["created_at"][:10], (it["description"] or "")[:60].replace("\n", " ")))
        print()
elif mode == "ax":
    DR = sys.argv[2]
    for p in ax.get(DR, [])[:8]:
        pid = p["id"].rstrip("/").split("/")[-1]
        dup = "DUP" if pid in seen_papers else "NEW"
        print("%s|%s|%s|%s" % (dup, p["cat"], p["published"][:10], p["title"][:95]))
print("SEEN_REPOS=%d SEEN_PAPERS=%d" % (len(seen_repos), len(seen_papers)))
