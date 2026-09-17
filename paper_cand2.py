#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""paper_cand2.py v2 — 修正 id 语义 bug 后重出候选

★ v1 的 bug: `d.get("id")` 在 labs_papers.jsonl 里是【内部序号】不是 arXiv id
  ⇒ 输出 "arxiv=2" 这种假标识。判据: arXiv id 必须能被正则匹配。
"""
import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = r"D:\hermes\hermes-data\profiles\qqbot3"
RES = os.path.join(BASE, "knowledge_base", "research")
ARXIV = re.compile(r"^\s*(?:arXiv:)?(\d{4}\.\d{4,5})(v\d+)?\s*$", re.I)

rows = []
for p in glob.glob(os.path.join(BASE, "data", "labs_papers*.jsonl")) + \
         glob.glob(os.path.join(BASE, "data", "paper_tracker.jsonl")) + \
         glob.glob(os.path.join(BASE, "data", "papers_multisource.jsonl")):
    for line in open(p, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if not isinstance(d, dict) or not d.get("title"):
            continue
        # ★ 只有【真能被 arXiv 正则匹配】的才算 arXiv id
        aid = ""
        for k in ("arxiv_id", "arxiv", "id"):
            m = ARXIV.match(str(d.get(k) or ""))
            if m:
                aid = m.group(1)
                break
        doi = str(d.get("doi") or "")
        rows.append({"title": str(d["title"]).strip(),
                     "arxiv": aid,
                     "doi": doi if doi.startswith("http") else "",
                     "date": str(d.get("published") or d.get("date") or "")[:10],
                     "lab": str(d.get("lab") or ""),
                     "venue": str(d.get("venue") or "")[:40],
                     "topic": str(d.get("topic") or "")[:30],
                     "src": os.path.basename(p)})

seen = {}
for r in rows:
    k = re.sub(r"[^a-z0-9]", "", r["title"].lower())[:70]
    if k and k not in seen:
        seen[k] = r

corpus = []
for p in glob.glob(os.path.join(RES, "*.md")):
    try:
        corpus.append(open(p, encoding="utf-8", errors="replace").read().lower())
    except Exception:
        pass

def archived(r):
    if r["arxiv"] and any(r["arxiv"] in t for t in corpus):
        return True
    ws = re.findall(r"[a-z]{5,}", r["title"].lower())[:6]
    return bool(ws) and any(sum(1 for w in ws if w in t) >= max(3, len(ws) - 1) for t in corpus)

AI = re.compile(r"(llm|language model|\bagent|transformer|attention|kv cache|quantiz|"
                r"reinforcement|rlhf|distill|reasoning|inference|neural|diffusion|"
                r"embedding|retriev|\brag\b|\bmoe\b|benchmark|alignment|interpretab|"
                r"multimodal|self-improv|world model)", re.I)
MED = re.compile(r"(patient|clinical|disease|tumor|cardio|neuro|brain|cancer|surgery|"
                 r"covid|health|plasma|stellar|galax|protein|gene|molecul)", re.I)

cand = [r for r in seen.values() if not archived(r) and AI.search(r["title"])
        and not MED.search(r["title"])]
cand.sort(key=lambda x: x["date"], reverse=True)

L = ["  台账去重 %d 篇 | AI 相关且未深研 %d 篇" % (len(seen), len(cand)), ""]
for r in cand[:24]:
    tid = ("arXiv:" + r["arxiv"]) if r["arxiv"] else (r["doi"][:52] if r["doi"] else "—")
    L.append("[%s] %s" % (r["date"] or "----------", r["title"][:66]))
    L.append("        %s | %s %s" % (tid, r["lab"] or r["src"], r["venue"]))
open(os.path.join(BASE, "data", "_ai_cand2.txt"), "w", encoding="utf-8").write("\n".join(L))
json.dump(cand, open(os.path.join(BASE, "data", "ai_deep_candidates.json"), "w",
                     encoding="utf-8"), ensure_ascii=False, indent=1)
print("OK  AI候选 %d 篇 -> data/_ai_cand2.txt" % len(cand))
print("   其中有 arXiv id 的: %d 篇" % sum(1 for r in cand if r["arxiv"]))
