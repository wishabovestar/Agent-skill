# -*- coding: utf-8 -*-
import urllib.request, ssl, json, re, html, time
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
def fetch(u,timeout=20):
    return urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":UA,"Accept-Language":"zh-CN,zh;q=0.9"}),timeout=timeout).read().decode("utf-8","ignore")
def tf(u,**k):
    for a in range(2):
        try: return fetch(u,**k)
        except Exception as e:
            if a==1: return "__ERR__ "+str(e)[:70]
            time.sleep(2)
def clean(s):
    s=re.sub(r"<script.*?</script>","",s or "",flags=re.S); s=re.sub(r"<style.*?</style>","",s,flags=re.S)
    s=re.sub(r"<[^>]+>"," ",s); s=html.unescape(s); return re.sub(r"\s+"," ",s).strip()
urls={
 "ivdc":"https://ivdc.chinacdc.cn/cnic/",
 "ivdc_flu":"https://ivdc.chinacdc.cn/cnic/zyzx/lgzb/",
 "cdc_home":"https://www.chinacdc.cn/",
 "cdc_flu2":"https://www.chinacdc.cn/jkzt/crb/zl/lgxy/index.html",
}
for k,u in urls.items():
    r=tf(u)
    print(f"=== {k} {'ERR' if str(r).startswith('__ERR__') else 'OK '+str(len(r))} ===")
    if not str(r).startswith("__ERR__"):
        t=clean(r)
        # extract dated titles
        hits=re.findall(r"(202\d年\d{1,2}月[^ ]{0,30}(?:周报|情况|概要|监测|疫情)[^ ]{0,20})", t)
        hits+=re.findall(r"(流感[^ ]{0,30})", t)[:6]
        hits+=re.findall(r"(新冠[^ ]{0,30}情况[^ ]{0,20})", t)
        for x in list(dict.fromkeys(hits))[:10]: print("   •",x[:90])
