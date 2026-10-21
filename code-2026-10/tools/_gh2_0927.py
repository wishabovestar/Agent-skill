import urllib.request, ssl, re, json, sys
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url, timeout=40):
    req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8","replace")
try:
    h=get("https://github.com/trending?since=daily")
    arts=re.findall(r'<article class="Box-row">(.*?)</article>', h, re.S)
    for a in arts[:20]:
        m=re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', a)
        d=re.search(r'<p class="col-9[^"]*">(.*?)</p>', a, re.S)
        st=re.search(r'([\d,]+)\s*stars today', a)
        tot=re.search(r'href="/[^"]+/stargazers"[^>]*>\s*([\d,]+)', a)
        lang=re.search(r'itemprop="programmingLanguage">([^<]+)<', a)
        name=m.group(1) if m else "?"
        desc=re.sub(r'<[^>]+>','',d.group(1)).strip()[:100] if d else ""
        print(f"{name} || {lang.group(1) if lang else '-'} || +{st.group(1) if st else '?'} || {desc}")
except Exception as e:
    print("ERR", repr(e))
