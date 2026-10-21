# -*- coding: utf-8 -*-
"""从 RSC/JS 载荷里抽正文（warp.dev 博客是客户端渲染）"""
import sys, io, re, json, html
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
D = Path("D:/hermes/analysis/_x5")
raw = (D / "warp_post.html").read_text(encoding="utf-8", errors="ignore")

# 1) 找所有双引号字符串里含空格的英文长串
cands = re.findall(r'"((?:[^"\\]|\\.){80,3000})"', raw)
txt, seen = [], set()
for c in cands:
    try:
        s = json.loads('"' + c + '"')
    except Exception:
        continue
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    if re.search(r"[A-Za-z]{4}\s+[A-Za-z]{4}\s+[A-Za-z]{4}", s) and not s.startswith("http"):
        s = re.sub(r"\s+", " ", s).strip()
        if s not in seen:
            seen.add(s); txt.append(s)
body = "\n".join(txt)
(D / "warp_body.txt").write_text(body, encoding="utf-8")
print("CHUNKS", len(txt), "CHARS", len(body))

# 2) 数字句 + 关键词上下文
sents = re.split(r"(?<=[.!?])\s+", body)
good = [s for s in sents if 40 < len(s) < 500 and re.search(r"\d", s)]
print("NUM_SENTS", len(good))
for i, s in enumerate(good[:40], 1):
    print(f"{i}. {s[:300]}")
