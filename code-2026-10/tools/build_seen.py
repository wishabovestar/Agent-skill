import json, glob, os, re

roots = ["D:/hermes/data/agent_knowledge", "D:/hermes/data/math_knowledge",
         "D:/hermes/data/book_knowledge", "D:/hermes/data/physics_knowledge"]
files = []
for r in roots:
    if os.path.isdir(r):
        files += glob.glob(r + "/**/*.json", recursive=True)

seen = set()

def walk(o, src):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("full_name", "repo", "repository", "repo_name") and isinstance(v, str) and "/" in v:
                seen.add(v.strip().lower())
            elif k == "name" and isinstance(v, str) and "/" in v and v.count("/") == 1:
                seen.add(v.strip().lower())
            walk(v, src)
    elif isinstance(o, list):
        for v in o:
            walk(v, src)

used = 0
for f in files:
    lf = f.replace("\\", "/")
    if "/tmp/" in lf or "/Tmp/" in lf:
        continue
    try:
        data = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    used += 1
    walk(data, f)

print("SEEN=%d from %d files (of %d)" % (len(seen), used, len(files)))
out = "D:/hermes/analysis/seen_repos.json"
json.dump(sorted(seen), open(out, "w", encoding="utf-8"))
print("written", out)
