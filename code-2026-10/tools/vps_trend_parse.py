#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""GitHub Trending提取 (py2/py3兼容)"""
import re, sys

html = open("/tmp/trend.html", "rb").read().decode("utf-8", errors="ignore")
# 宽松模式: 找所有 repo 形式的 href
repos = re.findall(r'href="/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"', html)
seen = set()
count = 0
skip = ("features", "topics", "collections", "login", "signup",
        "sponsors", "marketplace", "settings", "orgs", "about",
        "pricing", "team", "enterprise", "customer-stories")
for r in repos:
    if r not in seen and not r.startswith(skip):
        seen.add(r)
        count += 1
        if count <= 15:
            print("  " + r)
print("TOTAL:" + str(count))
