# -*- coding: utf-8 -*-
import json, re, html
raw=json.load(open("D:/hermes/analysis/_b1013_news_raw.json",encoding="utf-8"))
def clean(s):
    s=re.sub(r"<script.*?</script>","",s or "",flags=re.S); s=re.sub(r"<style.*?</style>","",s,flags=re.S)
    s=re.sub(r"<[^>]+>"," ",s); s=html.unescape(s); return re.sub(r"\s+"," ",s).strip()

# WHO DON
print("=== WHO DON ===")
try:
    j=json.loads(raw["who_don"])
    vals=j.get("value",j) if isinstance(j,dict) else j
    for it in (vals[:10] if isinstance(vals,list) else []):
        t=it.get("Title") or it.get("title") or ""
        d=(it.get("PublicationDateAndTime") or it.get("PublicationDate") or "")[:10]
        print(f" [{d}] {t[:130]}")
except Exception as e:
    print("parse err",str(e)[:120]); print(str(raw.get("who_don"))[:300])

print("\n=== ECDC ===")
t=clean(raw.get("ecdc",""))
for h in list(dict.fromkeys(re.findall(r"(?:Avian influenza|Influenza|COVID|measles|Mpox|mpox|Cholera|dengue|Marburg|Diphtheria|Respiratory)[^.]{5,120}", t, re.I)))[:14]:
    print(" •",h[:150])

print("\n=== CIDRAP ===")
t=clean(raw.get("cidrap",""))
for h in list(dict.fromkeys(re.findall(r"[A-Z][^.|]{20,130}", t)))[:22]:
    if any(w in h for w in ["flu","Flu","COVID","Covid","virus","measles","mpox","H5","bird","outbreak","vaccine","RSV","avian"]):
        print(" •",h[:150])

print("\n=== Nature (titles) ===")
t=clean(raw.get("nature",""))
for h in list(dict.fromkeys(re.findall(r"<title>(.*?)</title>|<title><!\[CDATA\[(.*?)\]\]></title>", raw.get("nature",""), re.S)))[:0]: pass
for h in list(dict.fromkeys(re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", raw.get("nature",""), re.S)))[:16]:
    print(" •",h[:150])

print("\n=== Ars Technica (titles) ===")
for h in list(dict.fromkeys(re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", raw.get("arstech",""), re.S)))[:14]:
    print(" •",h[:140])

print("\n=== thepaper (headlines) ===")
t=clean(raw.get("thepaper",""))
for h in list(dict.fromkeys(re.findall(r'"name":"([^"]{8,60})"', raw.get("thepaper",""))))[:18]:
    print(" •",h[:90])

print("\n=== 36kr ===")
t=raw.get("36kr","")
for h in list(dict.fromkeys(re.findall(r'"title":"([^"]{8,80})"', t)))[:18]:
    print(" •",h[:100])

print("\n=== ithome (titles) ===")
for h in list(dict.fromkeys(re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", raw.get("ithome",""), re.S)))[:16]:
    print(" •",h[:140])

print("\n=== sina_tech ===")
try:
    j=json.loads(raw.get("sina_tech","{}"))
    for it in (j.get("result",{}).get("data",[]) or [])[:14]:
        print(f" • {it.get('title','')[:120]}")
except Exception as e:
    print("err",str(e)[:100])

print("\n=== SMM 碳酸锂 hits ===")
t=clean(raw.get("smm",""))
hits=list(dict.fromkeys(re.findall(r"碳酸锂[^。；|\s]{0,40}", t)))
print(" | ".join(hits[:20])[:1500])
