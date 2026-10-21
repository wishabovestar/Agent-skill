import urllib.request, ssl, json, re, os, datetime

ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_daily_1009_gh.json")

def get(url, timeout=40, hdr=None):
    h={"User-Agent":"Mozilla/5.0","Accept":"*/*"}
    if hdr: h.update(hdr)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8","replace")

res={}
# 1) Trending page (HTML)
try:
    html = get("https://github.com/trending?since=daily")
    # split by article
    arts = re.findall(r'<article class="Box-row">(.*?)</article>', html, re.S)
    trend=[]
    for a in arts[:15]:
        m = re.search(r'<h2[^>]*>.*?<a[^>]*href="/([^"]+)"', a, re.S)
        desc = re.search(r'<p class="col-9[^"]*"[^>]*>(.*?)</p>', a, re.S)
        stars = re.findall(r'<a[^>]*href="/[^"]+/stargazers"[^>]*>(.*?)</a>', a, re.S)
        today = re.search(r'([\d,]+)\s*stars today', a)
        full = m.group(1).strip() if m else "?"
        d = re.sub(r'<[^>]+>',' ', desc.group(1)) if desc else ""
        d = re.sub(r'\s+',' ', d).strip()
        st = re.sub(r'<[^>]+>','', stars[0]).strip() if stars else "?"
        td = today.group(1) if today else "?"
        trend.append({"repo":full,"desc":d[:200],"stars":st,"today":td})
    res["trending"]=trend
    print("### GITHUB TRENDING (daily)")
    for t in trend:
        print(" -",t["repo"],"| +",t["today"],"today | total",t["stars"])
        print("   ",t["desc"][:140])
except Exception as e:
    print("trending ERR", repr(e)); res["trending"]=[]

# 2) New repos created in last 7 days, most stars
try:
    since=(datetime.date.today()-datetime.timedelta(days=7)).isoformat()
    data=json.loads(get("https://api.github.com/search/repositories?q=created:%3E"+since+"&sort=stars&order=desc&per_page=12"))
    res["new"]=[{"repo":i["full_name"],"stars":i["stargazers_count"],"desc":i.get("description") or "","url":i["html_url"],"lang":i.get("language")} for i in data.get("items",[])]
    print("\n### NEW REPOS (last 7d, most stars)")
    for i in res["new"]:
        print(" -",i["repo"],"| ",i["stars"],"stars | ",i["lang"])
        print("   ",i["desc"][:150])
except Exception as e:
    print("new ERR", repr(e)); res["new"]=[]

json.dump(res, open(OUT,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("\nsaved", OUT)
