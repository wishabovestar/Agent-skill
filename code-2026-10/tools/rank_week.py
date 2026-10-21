# -*- coding: utf-8 -*-
"""把本周 575 篇按「与本机关注点的相关度」打分排序，输出一张可读的候选表。"""
import json
import re
import io

db = json.load(open("D:/hermes/analysis/_week_papers.json", encoding="utf-8"))["papers"]

BUCKET_W = {"memory": 3.0, "multiagent": 2.2, "tool": 2.2, "longctx": 2.0, "mlip": 2.4,
            "battery": 2.4, "rl": 1.4, "attn": 1.2, "calib": 1.3, "eval": 0.9}

# 关注点（来自用户画像 + 本机在做的活）
BONUS = [
    (r"consolidat", 2.0), (r"memory (?:system|architecture|bank|os)", 1.6),
    (r"\bbenchmark\b", 1.2), (r"\bdataset\b", 1.0), (r"\bsurvey\b", 1.4),
    (r"open[- ]?sourc|we release|code is available", 1.0),
    (r"long[- ]?horizon", 1.2), (r"token (?:efficien|budget|cost)", 1.6),
    (r"kv[- ]?cache", 1.4), (r"sparse attention", 1.4),
    (r"machine learning potential|interatomic|foundation model", 1.6),
    (r"electrode|lithium|solid electrolyte|drying|calendering", 1.6),
    (r"\bscaling law", 1.0), (r"test[- ]time", 1.0),
    (r"failure|pitfall|limitation|negative result", 0.8),
    (r"\btheory\b|provabl|guarantee", 0.8),
]
PENALTY = [(r"position paper|opinion|comment on", -1.5),
           (r"medical|clinical|patient|social media|legal|finance", -2.5),
           (r"vision[- ]language|image generation|video generation|speech", -1.5)]


def score(p):
    s = sum(BUCKET_W.get(b, 0) for b in p["buckets"])
    text = (p["title"] + " " + p["abs"]).lower()
    for pat, w in BONUS:
        if re.search(pat, text):
            s += w
    for pat, w in PENALTY:
        if re.search(pat, text):
            s += w
    # 纯理论/纯应用微调
    if re.search(r"agent|llm|language model", text):
        s += 1.0
    return round(s, 2)


for p in db:
    p["score"] = score(p)
db.sort(key=lambda x: -x["score"])

lines = []
for i, p in enumerate(db[:60], 1):
    lines.append(f"{i:02d}. [{p['score']:.1f}] {p['id']} | {','.join(p['buckets'])}")
    lines.append(f"    {p['title']}")
    lines.append(f"    {p['published'][:10]} | {len(p['authors'])} authors | {','.join(p['cats'][:2])}")
    lines.append(f"    {p['abs'][:340]}")
    lines.append("")
io.open("D:/hermes/analysis/_week_ranked.txt", "w", encoding="utf-8").write("\n".join(lines))
print("papers", len(db), "written", len(lines))
