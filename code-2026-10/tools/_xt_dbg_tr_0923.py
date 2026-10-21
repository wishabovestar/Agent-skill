import re
html=open("D:/hermes/analysis/_xt0923/trending_daily.html",encoding="utf-8",errors="ignore").read()
b=html.split('<h2 class="h3 lh-condensed">')[1]
txt=re.sub(r"<[^>]+>"," ",b)
txt=re.sub(r"\s+"," ",txt)
print(txt[:300])
print("---")
i=html.find("stars today")
print(re.sub(r"<[^>]+>"," ",html[i-260:i+30]).replace("  "," ")[-260:])
