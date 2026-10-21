import re, html, urllib.request, ssl, sys
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
def fetch(url):
    try:
        d = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30, context=ctx).read()
        for enc in ("utf-8","gbk","gb18030"):
            try:
                return d.decode(enc)
            except Exception:
                continue
        return d.decode("utf-8","ignore")
    except Exception as e:
        return f"__ERR__ {e}"

urls = sys.argv[1:]
for u in urls:
    t = fetch(u)
    print("#"*20, u)
    if t.startswith("__ERR__"):
        print(t); continue
    t = re.sub(r'<script.*?</script>', ' ', t, flags=re.S)
    t = re.sub(r'<style.*?</style>', ' ', t, flags=re.S)
    txt = re.sub(r'<[^>]+>', ' ', t)
    txt = html.unescape(re.sub(r'\s+', ' ', txt)).strip()
    print(txt[:2500])
