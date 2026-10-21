# -*- coding: utf-8 -*-
import urllib.request, ssl, re, html, time
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
def fetch(u,timeout=20):
    return urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":UA,"Accept-Language":"zh-CN,zh;q=0.9"}),timeout=timeout).read().decode("utf-8","ignore")
def clean(s):
    s=re.sub(r"<script.*?</script>","",s or "",flags=re.S); s=re.sub(r"<style.*?</style>","",s,flags=re.S)
    s=re.sub(r"<[^>]+>"," ",s); s=html.unescape(s); return re.sub(r"\s+"," ",s).strip()
h=fetch("https://www.chinacdc.cn/")
links=re.findall(r'href="([^"]+)"[^>]*>([^<]{4,50})</a>', h)
targets=[(u,t) for u,t in links if any(w in t for w in ["流感","疫情","监测","新冠","传染"])]
print("links:")
for u,t in targets[:20]: print("  ",t,"->",u[:100])
# fetch flu weekly
cands=[u for u,t in targets if "流感" in t or "周报" in t][:3]
cands=["https://www.chinacdc.cn/jkzt/crb/zl/lgxy/","https://ivdc.chinacdc.cn/cnic/zyzx/lgzb/"]
for u in cands:
    try:
        if u.startswith("/"): u="https://www.chinacdc.cn"+u
        r=fetch(u)
        t=clean(r)
        hits=re.findall(r"(2026年[^ ]{0,40}(?:周|月)[^ ]{0,20})", t)
        print(f"--- {u[:80]} OK ---")
        print("  ", " | ".join(list(dict.fromkeys(hits))[:8]))
        print("  snip:", t[:280])
    except Exception as e:
        print(f"--- {u[:80]} ERR {str(e)[:50]}")
