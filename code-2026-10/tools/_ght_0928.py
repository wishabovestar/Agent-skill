import urllib.request, ssl, re, json, sys
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url, timeout=60, headers=None):
    h={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
       "Accept-Language":"en-US,en;q=0.9"}
    if headers: h.update(headers)
    req=urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8","replace")

trending=[]
for since in ["daily"]:
    for attempt in range(3):
        try:
            h=get(f"https://github.com/trending?since={since}"); break
        except Exception as e:
            print("retry",since,repr(e))
    else:
        continue
    arts=re.findall(r'<article class="Box-row">(.*?)</article>', h, re.S)
    print("=== TRENDING", since, "count", len(arts))
    for a in arts[:25]:
        m=re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', a)
        d=re.search(r'<p class="col-9[^"]*">(.*?)</p>', a, re.S)
        s=re.search(r'stargazers</a>\s*</span>\s*([\d,]+)', a)
        st=re.search(r'(\d[\d,]*)\s*stars today', a)
        name=m.group(1) if m else "?"
        desc=re.sub(r'<[^>]+>','',d.group(1)).strip()[:120] if d else ""
        line=f"{name} | {s.group(1) if s else '?'} | +{st.group(1) if st else '?'} today | {desc}"
        print("  ", line)
        trending.append(line)
json.dump({"trending":trending}, open("_ght_0928.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED", len(trending))
