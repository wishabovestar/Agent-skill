import json, urllib.request, urllib.parse, ssl, re, sys
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8","replace")
out={}
# GitHub trending
try:
    h=get("https://github.com/trending?since=daily")
    repos=re.findall(r'<h2 class="h3 lh-condensed">\s*<a href="/([^"]+)"', h)
    print("GH_TRENDING:", repos[:25])
    out["gh"]=repos[:25]
except Exception as e:
    print("GH ERR", e)
print("PYOK")
