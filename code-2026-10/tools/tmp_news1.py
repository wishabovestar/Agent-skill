import re, html, urllib.request, ssl, json, sys
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def get(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=35, context=ctx).read().decode("utf-8","ignore")

# --- GitHub trending ---
print("###GITHUB###")
t = get("https://github.com/trending?since=daily")
arts = re.split(r'<article class="Box-row">', t)
for a in arts[1:26]:
    m = re.search(r'<h2 class="h3 lh-condensed">\s*<a href="/([^"]+)"', a)
    d = re.search(r'<p class="col-9 color-fg-muted my-1 pr-4">\s*(.*?)\s*</p>', a, re.S)
    s = re.search(r'>([\d,]+)</a>\s*</span>\s*<span[^>]*aria-label="fork"', a)
    st = re.search(r'aria-label="star"[^>]*>\s*([\d,]+)', a)
    if not st:
        st = re.search(r'stargazers"[^>]*>\s*([\d,]+)', a)
    lg = re.search(r'itemprop="programmingLanguage">([^<]+)<', a)
    name = m.group(1) if m else "?"
    desc = html.unescape(re.sub(r'<[^>]+>','',d.group(1))).strip() if d else ""
    stars = st.group(1) if st else "?"
    lang = lg.group(1) if lg else ""
    print(f"{name}|{stars}|{lang}|{desc[:140]}")

# --- arXiv API ---
def arxiv(q, n=6, sort="submittedDate"):
    url = f"http://export.arxiv.org/api/query?search_query={urllib.parse.quote(q)}&sortBy={sort}&sortOrder=descending&max_results={n}"
    try:
        x = get(url)
    except Exception as e:
        print("ERR", q, e); return
    entries = re.findall(r'<entry>(.*?)</entry>', x, re.S)
    for e in entries:
        ti = re.search(r'<title>(.*?)</title>', e, re.S)
        pub = re.search(r'<published>(.*?)</published>', e)
        idm = re.search(r'<id>(.*?)</id>', e)
        print(f"  [{pub.group(1)[:10] if pub else '?'}] {html.unescape(ti.group(1)).strip()[:140] if ti else '?'} :: {idm.group(1) if idm else ''}")

import urllib.parse
print("###ARXIV_LITHIUM###")
arxiv('all:"lithium battery" OR all:"solid state battery" OR all:"silicon anode"', 8)
print("###ARXIV_AI###")
arxiv('cat:cs.LG OR cat:cs.AI', 10)
print("###ARXIV_TRANSFORMER###")
arxiv('all:transformer OR all:diffusion OR all:"graph neural network" OR all:"large language model"', 10)
