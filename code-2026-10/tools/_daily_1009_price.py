import re, html, urllib.request, json, os, time
PROXY="http://127.0.0.1:8899"
opener=urllib.request.build_opener(urllib.request.ProxyHandler({"http":PROXY,"https":PROXY}))
def fetch(url, timeout=25):
    req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36","Accept-Language":"zh-CN,zh;q=0.9"})
    with opener.open(req, timeout=timeout) as r:
        raw=r.read()
    for e in ["utf-8","gbk","gb18030"]:
        try: return raw.decode(e,"strict")
        except Exception: continue
    return raw.decode("utf-8","replace")

for name,u in [("100PPI_锂","https://www.100ppi.com/mprice/"),
               ("SMM","https://www.smm.cn/"),
               ("生意社锂","https://www.100ppi.com/sf/677.html")]:
    try:
        d=fetch(u)
        txt=re.sub(r'<script.*?</script>','',d,flags=re.S)
        txt=re.sub(r'<[^>]+>',' ',txt); txt=html.unescape(re.sub(r'\s+',' ',txt))
        hits=[m for m in re.findall(r'.{0,40}碳酸锂.{0,60}', txt)][:6]
        print("###",name,len(d))
        for h in hits: print("   ",h[:140])
    except Exception as e:
        print("###",name,"ERR",repr(e)[:120])
