import re, html, sys, os
for fn in sys.argv[1:]:
    if not os.path.exists(fn):
        print("MISS", fn); continue
    d = open(fn, "rb").read()
    t = None
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            t = d.decode(enc); break
        except Exception:
            continue
    if t is None: t = d.decode("utf-8", "ignore")
    print("#" * 20, fn)
    t = re.sub(r'<script.*?</script>', ' ', t, flags=re.S)
    t = re.sub(r'<style.*?</style>', ' ', t, flags=re.S)
    txt = html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', t))).strip()
    print(txt[:2200])
    print()
