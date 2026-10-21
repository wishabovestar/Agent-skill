# -*- coding: utf-8 -*-
import re
RAW = r"D:/hermes/data/agent_knowledge/算法/tmp/trending_vps_1011.txt"
html = open(RAW, encoding="utf-8").read()
parts = re.split(r"===XX:(\w+)===XX", html)
daily = parts[2]
blocks = re.split(r'<article class="Box-row">', daily)[1:]
b = blocks[0]
i = b.find('h3 lh-condensed')
seg = b[i:i+700]
seg = re.sub(r'data-hydro-click="[^"]*"', 'HREF_ATTR', seg)
seg = re.sub(r'\s+', ' ', seg)
print("--- h2 cleaned ---")
print(seg[:500])
# stars total region: strip and search
txt = re.sub(r"<[^>]+>", " ", b)
txt = re.sub(r"\s+", " ", txt).strip()
print("--- stripped text tail ---")
print(txt[-320:])
