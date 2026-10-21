import re, html
t = open(r"D:/hermes/analysis/gh_trending.html", encoding="utf-8", errors="ignore").read()
blocks = t.split('<article class="Box-row">')[1:26]
for a in blocks:
    m = re.search(r'<h2 class="h3 lh-condensed">\s*<a href="/([^"]+)"', a)
    name = m.group(1) if m else "?"
    d = re.search(r'<p class="col-9[^"]*">\s*(.*?)</p>', a, re.S)
    desc = html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', d.group(1)))).strip() if d else ""
    st = re.search(r'aria-label="star"[^>]*>\s*<svg[^>]*>.*?</svg>\s*([\d,]+)', a, re.S)
    if not st:
        st = re.search(r'>\s*([\d,]+)\s*</a>', a)
    lg = re.search(r'itemprop="programmingLanguage">\s*([^<]+?)\s*<', a)
    today = re.search(r'([\d,]+)\s*stars today', a)
    print(f"{name} | total={st.group(1) if st else '?'} | today={today.group(1) if today else '?'} | {lg.group(1) if lg else ''} | {desc[:140]}")
