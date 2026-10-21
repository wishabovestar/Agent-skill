import re, html, urllib.request, json, os, time
PROXY="http://127.0.0.1:8899"
opener=urllib.request.build_opener(urllib.request.ProxyHandler({"http":PROXY,"https":PROXY}))
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"_daily_1009_cn.json")

def fetch(url, timeout=25, enc=None):
    req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept-Language":"zh-CN,zh;q=0.9"})
    with opener.open(req, timeout=timeout) as r:
        raw=r.read()
    for e in ([enc] if enc else ["utf-8","gbk","gb18030"]):
        try: return raw.decode(e,"strict")
        except Exception: continue
    return raw.decode("utf-8","replace")

SITES = {
 "ITDCW_电池网":"https://www.itdcw.com/",
 "GGLB_高工锂电":"https://www.gg-lb.com/",
 "CLS_财联社":"https://www.cls.cn/",
 "SMM_上海有色":"https://news.smm.cn/lithium",
 "100PPI_碳酸锂":"https://www.100ppi.com/mprice/detail-1-1019.html",
 "OFWEEK_锂电":"https://libattery.ofweek.com/",
}
res={}
for k,u in SITES.items():
    try:
        d=fetch(u)
        # extract anchor texts that look like headlines
        links=re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', d, re.S)
        heads=[]
        for href,txt in links:
            t=html.unescape(re.sub(r'<[^>]+>',' ',txt)).strip()
            t=re.sub(r'\s+',' ',t)
            if 12<=len(t)<=80 and not t.startswith('http') and re.search(r'[\u4e00-\u9fff]',t):
                if not any(x in t for x in ['登录','注册','首页','关于','联系','广告','版权','下载','客户端','微博','微信']):
                    heads.append((t,href))
        # dedupe
        seen=set(); uh=[]
        for t,h in heads:
            if t in seen: continue
            seen.add(t); uh.append((t,h))
        res[k]={"url":u,"heads":uh[:35]}
        print("\n###",k,"->",len(uh),"headlines")
        for t,h in uh[:22]:
            print("  -",t[:70])
    except Exception as e:
        res[k]={"url":u,"err":repr(e)[:150]}
        print("\n###",k,"ERR",repr(e)[:150])
json.dump(res, open(OUT,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("\nsaved",OUT)
