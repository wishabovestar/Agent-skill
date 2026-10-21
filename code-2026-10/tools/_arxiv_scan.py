#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_arxiv_scan.py —— 解析 arXiv API 返回的 Atom XML，紧凑打印（日期/ID/标题/分类）。
用法: python _arxiv_scan.py _arxiv_agentmem.xml [更多xml...]
"""
from __future__ import annotations

import pathlib
import re
import sys


def parse(p: str) -> list[dict]:
    t = pathlib.Path(p).read_text(encoding="utf-8", errors="replace")
    out = []
    for e in re.findall(r"<entry>(.*?)</entry>", t, re.S):
        def g(tag: str) -> str:
            m = re.search(rf"<{tag}>(.*?)</{tag}>", e, re.S)
            return " ".join(m.group(1).split()) if m else ""
        cats = re.findall(r'<category[^>]*term="([^"]+)"', e)
        au = re.findall(r"<name>(.*?)</name>", e, re.S)
        out.append({
            "id": g("id").rsplit("/", 1)[-1],
            "pub": g("published")[:10],
            "upd": g("updated")[:10],
            "title": g("title"),
            "cats": ",".join(cats[:4]),
            "nau": len(au),
            "abs": g("summary"),
        })
    return out


for p in sys.argv[1:]:
    rows = parse(p)
    print("=" * 24, p, f"（{len(rows)} 条）")
    for r in rows:
        print(f'{r["pub"]} {r["id"]:>12}  {r["title"][:150]}  [{r["cats"]}]')
