import re, html, urllib.request, ssl, json
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=35, context=ctx).read().decode("utf-8","ignore")

t = get("https://github.com/trending?since=daily")
# split on repo link anchors
blocks = re.split(r'<article class="Box-row">', t)[1:26]
print("###GITHUB###")
for a in blocks:
    m = re.search(r'href="/([^"/]+/[^"/]+)"', a)
    name = m.group(1) if m else "?"
    d = re.search(r'<p class="col-9[^"]*">\s*(.*?)</p>', a, re.S)
    desc = html.unescape(re.sub(r'\s+',' ',re.sub(r'<[^>]+>','',d.group(1)))).strip() if d else ""
    st = re.search(r'star[^>]*>\s*([\d,]+)\s*<', a)
    lg = re.search(r'itemprop="programmingLanguage">\s*([^<]+?)\s*<', a)
    print(f"{name} | stars={st.group(1) if st else '?'} | lang={lg.group(1) if lg else ''} | {desc[:150]}")
# today stars gained
tg = re.findall(r'([\d,]+)\s*stars today', t)
print("stars_today:", tg[:25])
