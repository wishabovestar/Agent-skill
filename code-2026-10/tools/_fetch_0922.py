import urllib.request, ssl, re, html
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url, timeout=30):
    req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8","replace")
def txt(h):
    h=re.sub(r'<script.*?</script>','',h,flags=re.S)
    h=re.sub(r'<style.*?</style>','',h,flags=re.S)
    h=re.sub(r'<[^>]+>',' ',h)
    h=html.unescape(h)
    h=re.sub(r'\s+',' ',h)
    return h.strip()
for u in ["https://m.mysteel.com/zta/tansuanli/","https://www.cbcie.com/lithium/price/content/72827"]:
    try:
        t=txt(get(u))
        # find price-like context
        print("=== ",u)
        idx=0
        for m in re.finditer(r'.{60}(元/吨|万元/吨).{40}', t):
            print("  …", m.group(0).strip()[:140])
            idx+=1
            if idx>8: break
    except Exception as e:
        print("ERR", u, repr(e))
