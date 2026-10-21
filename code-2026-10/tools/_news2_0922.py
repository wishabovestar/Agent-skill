import json, urllib.request, ssl, re
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url, timeout=30, headers=None):
    h={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
    if headers: h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8","replace")

# 1) GitHub trending (new layout)
try:
    h=get("https://github.com/trending?since=daily")
    # capture repo links inside article/h2
    repos=re.findall(r'href="/([\w.\-]+/[\w.\-]+)"[^>]*data-hydro-click', h)
    if not repos:
        repos=re.findall(r'<a[^>]+href="/([\w.\-]+/[\w.\-]+)"[^>]*>\s*<span[^>]*class="text-normal"', h)
    if not repos:
        # fallback: any /owner/repo in h2 blocks
        blocks=re.findall(r'<h2[^>]*>(.*?)</h2>', h, re.S)
        for b in blocks:
            m=re.findall(r'href="/([\w.\-]+/[\w.\-]+)"', b)
            repos+=m
    seen=[]; 
    for r in repos:
        if r not in seen and '/' in r and not r.startswith('login') and not r.startswith('signup') and not r.startswith('features') and not r.startswith('topics') and not r.startswith('collections') and not r.startswith('sponsors') and not r.startswith('orgs'):
            seen.append(r)
    print("GH_TRENDING:", json.dumps(seen[:30], ensure_ascii=False))
except Exception as e:
    print("GH ERR", repr(e))
