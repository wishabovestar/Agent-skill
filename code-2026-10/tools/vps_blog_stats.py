#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""博客浏览统计 - 从nginx日志提取访问数据 (VPS端运行)"""
import re, json, os, time
from collections import Counter

LOG = "/etc/nginx/logs/cloudlink_access.log"
OUT = "/home/wwwroot/3DCEList/blog_stats.json"

def analyze():
    if not os.path.exists(LOG):
        return {"error": "log not found"}
    urls, agents, codes = Counter(), Counter(), Counter()
    with open(LOG, "rb") as f:
        for line in f:
            line = line.decode("utf-8", errors="ignore")
            m = re.match(r'(\S+) .*?"(GET|POST) (\S+) HTTP[^"]*" (\d+) .*?"(.*?)"', line)
            if not m: continue
            ip, method, url, code, ua = m.group(1), m.group(2), m.group(3), int(m.group(4)), m.group(5)
            urls[url] += 1
            codes[code] += 1
            if "blog" in url or url == "/":
                agents[ua[:50]] += 1
    bots = sum(v for k, v in agents.items() if any(b in k.lower() for b in ["zgrab", "redtail", "infrawatch", "masscan", "nmap", "bot", "curl", "python"]))
    data = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": sum(urls.values()),
        "status_codes": dict(codes),
        "top_urls": urls.most_common(15),
        "human_visits": max(0, sum(urls.values()) - bots),
        "bot_visits": bots,
        "blog_urls": {k: v for k, v in urls.items() if "blog" in k or k in ("/", "/blog.html")},
    }
    with open(OUT, "w") as f:
        json.dump(data, f, indent=2)
    return data

if __name__ == "__main__":
    print(json.dumps(analyze(), indent=2))
