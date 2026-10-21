# -*- coding: utf-8 -*-
import re
RAW = r"D:/hermes/data/agent_knowledge/算法/tmp/trending_vps_1011.txt"
html = open(RAW, encoding="utf-8").read()
parts = re.split(r"===XX:(\w+)===XX", html)
daily = parts[2]
blocks = re.split(r'<article class="Box-row">', daily)[1:]
b = blocks[0]
i = b.find('h3 lh-condensed')
print("--- h2 region ---")
print(b[i-30:i+360])
print("--- end region ---")
print(b[-800:])
