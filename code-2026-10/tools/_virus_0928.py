import urllib.request, ssl, re, json, sys
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url, timeout=45, headers=None):
    h={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
    if headers: h.update(headers)
    req=urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        raw=r.read()
    for enc in ("utf-8","gbk","latin-1"):
        try: return raw.decode(enc)
        except Exception: pass
    return raw.decode("utf-8","replace")

def strip(html):
    t=re.sub(r'<script.*?</script>','',html,flags=re.S|re.I)
    t=re.sub(r'<style.*?</style>','',t,flags=re.S|re.I)
    t=re.sub(r'<[^>]+>',' ',t)
    t=re.sub(r'&nbsp;',' ',t); t=re.sub(r'&amp;','&',t)
    t=re.sub(r'\s+',' ',t)
    return t

srcs = {
 "WHO_DON": "https://www.who.int/emergencies/disease-outbreak-news",
 "CIDRAP": "https://www.cidrap.umn.edu/",
 "ECDC": "https://www.ecdc.europa.eu/en/news-events",
 "OUTBREAK_NEWS": "https://outbreaknewstoday.com/",
 "FLU_TRACKER": "https://www.cdc.gov/flu/weekly/index.html",
}
out={}
for k,u in srcs.items():
    try:
        h=get(u)
        t=strip(h)
        out[k]=t[:4000]
        print("=====",k,"len",len(t))
        print(t[:1600])
    except Exception as e:
        print("ERR",k,repr(e))
        out[k]="ERR "+repr(e)
    sys.stdout.flush()
json.dump(out, open("_virus_0928.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED")
