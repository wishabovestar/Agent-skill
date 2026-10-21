import urllib.request, ssl, re, json, sys
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url, timeout=40, headers=None):
    h={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
    if headers: h.update(headers)
    req=urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8","replace")

daily=[]; trending=[]
for label, q in [("new14d","created:%3E2026-09-13"), ("new30d","created:%3E2026-08-28")]:
    try:
        j=json.loads(get(f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=15"))
        print("=== API", label)
        for it in j.get("items",[]):
            line=f"{it['full_name']} | star {it['stargazers_count']} | {(it.get('description') or '')[:110]}"
            print("  ", line)
            daily.append(line)
    except Exception as e:
        print("API ERR", label, repr(e))
    sys.stdout.flush()

try:
    h=get("https://github.com/trending?since=daily")
    print("=== TRENDING LEN", len(h))
    arts=re.findall(r'<article class="Box-row">(.*?)</article>', h, re.S)
    print("count", len(arts))
    for a in arts[:25]:
        m=re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', a)
        d=re.search(r'<p class="col-9[^"]*">(.*?)</p>', a, re.S)
        s=re.search(r'stargazers</a>\s*</span>\s*([\d,]+)', a)
        st=re.search(r'(\d[\d,]*)\s*stars today', a)
        name=m.group(1) if m else "?"
        desc=re.sub(r'<[^>]+>','',d.group(1)).strip()[:110] if d else ""
        print(f"  {name} | {s.group(1) if s else '?'} | +{st.group(1) if st else '?'} today | {desc}")
        trending.append(f"{name} | {s.group(1) if s else '?'} | +{st.group(1) if st else '?'} | {desc}")
except Exception as e:
    print("TREND ERR", repr(e))
json.dump({"api":daily,"trending":trending}, open("_gh_0927.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED")
