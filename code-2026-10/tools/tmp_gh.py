import sys, re, html, urllib.request, ssl
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    return urllib.request.urlopen(req, timeout=30, context=ctx).read().decode("utf-8","ignore")

t = get("https://github.com/trending?since=daily")
repos = re.findall(r'<h2 class="h3 lh-condensed">(.*?)</h2>', t, re.S)
descs = re.findall(r'<p class="col-9 color-fg-muted my-1 pr-4">\s*(.*?)\s*</p>', t, re.S)
stars = re.findall(r'aria-label="star">([\d,]+)</a>', t)
langs = re.findall(r'itemprop="programmingLanguage">([^<]+)<', t)
for i, r in enumerate(repos[:25]):
    m = re.search(r'href="/([^"]+)"', r)
    name = m.group(1) if m else "?"
    d = re.sub(r'<[^>]+>','',descs[i]).strip() if i < len(descs) else ""
    st = stars[i] if i < len(stars) else "?"
    lg = langs[i] if i < len(langs) else ""
    print(f"{i+1}\t{name}\t{st}\t{lg}\t{html.unescape(d)[:120]}")
