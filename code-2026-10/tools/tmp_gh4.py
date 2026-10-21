import re, html, sys
t = open(r"D:/hermes/analysis/gh_trending.html", encoding="utf-8", errors="ignore").read()
# names
names = re.findall(r'<h2 class="h3 lh-condensed">\s*<a href="/([^"]+)"[^>]*>', t)
blocks = t.split('<article class="Box-row">')[1:26]
for i, a in enumerate(blocks):
    nm = names[i] if i < len(names) else "?"
    d = re.search(r'<p class="col-9[^"]*">\s*(.*?)</p>', a, re.S)
    desc = html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', d.group(1)))).strip() if d else ""
    st = re.search(r'aria-label="star"[^>]*>\s*<svg[^>]*>.*?</svg>\s*([\d,]+)', a, re.S) or re.search(r'>\s*([\d,]+)\s*</a>', a)
    today = re.search(r'([\d,]+)\s*stars today', a)
    lg = re.search(r'itemprop="programmingLanguage">\s*([^<]+?)\s*<', a)
    print(f"{nm} | ★{st.group(1) if st else '?'} (+{today.group(1) if today else '?'} today) | {lg.group(1) if lg else ''} | {desc[:130]}")
