import ssl, urllib.request, sys, os, glob, json

ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE

def fetch(url, timeout=12, accept="text/html,application/xhtml+xml"):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36", "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", errors="ignore")

# 1) Probe trending locally
try:
    d = fetch("https://github.com/trending?since=daily", timeout=12)
    print(f"TRENDING_LOCAL=OK daily {len(d)} bytes")
except Exception as e:
    print(f"TRENDING_LOCAL=FAIL {type(e).__name__}: {str(e)[:80]}")

# 2) Count existing knowledge repos (seen set)
roots = ["D:/hermes/data/agent_knowledge", "D:/hermes/data/math_knowledge",
         "D:/hermes/data/book_knowledge", "D:/hermes/data/physics_knowledge"]
files = []
for r in roots:
    if os.path.isdir(r):
        files += glob.glob(r + "/**/*.json", recursive=True)
seen = set()
for f in files:
    if "\\tmp\\" in f or "/tmp/" in f:
        continue
    try:
        data = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    items = []
    if isinstance(data, dict):
        for k in ("items", "repos", "new", "papers", "results", "repositories"):
            if isinstance(data.get(k), list):
                items += data[k]
        if isinstance(data.get("data"), list):
            items += data["data"]
    elif isinstance(data, list):
        items = data
    for it in items:
        if not isinstance(it, dict):
            continue
        nm = it.get("full_name") or it.get("repo") or it.get("name")
        if nm:
            seen.add(str(nm).lower())
print(f"SEEN={len(seen)} from {len(files)} files")
