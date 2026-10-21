# -*- coding: utf-8 -*-
"""拉本周(20261012-20261019) arXiv 新论文，按选题桶去重合并，落 JSON + 候选清单。"""
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

DATE = "submittedDate:[202610120000 TO 202610192359]"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

BUCKETS = [
    ("memory", '(abs:"agent memory" OR abs:"memory system" OR abs:"long-term memory" OR abs:"memory consolidation")'),
    ("multiagent", '(abs:"multi-agent" OR abs:"multiagent" OR abs:"agent swarm" OR abs:"agent collaboration")'),
    ("tool", '(abs:"tool use" OR abs:"tool calling" OR abs:"function calling" OR abs:"computer use")'),
    ("rl", '(abs:"test-time" OR abs:"reinforcement learning" OR abs:"self-improvement" OR abs:"self-evolving")'),
    ("longctx", '(abs:"long-context" OR abs:"long context" OR abs:"context compression" OR abs:"context engineering")'),
    ("eval", '(abs:"LLM judge" OR abs:"LLM-as-a-judge" OR abs:"benchmark" OR abs:"evaluation")'),
    ("attn", '(abs:"sparse attention" OR abs:"linear attention" OR abs:"attention sink" OR abs:"KV cache")'),
    ("mlip", '(abs:"machine learning potential" OR abs:"interatomic potential" OR abs:"universal potential" OR abs:"foundation model" AND abs:"atomistic")'),
    ("battery", '(abs:"lithium" OR abs:"electrode" OR abs:"battery" OR abs:"solid electrolyte")'),
    ("calib", '(abs:"uncertainty" OR abs:"calibration" OR abs:"confidence" OR abs:"crux")'),
]


def fetch(q, n=120):
    url = ("https://export.arxiv.org/api/query?search_query="
           # ⚠️ safe 必须为空：把 [ ] " 全部编码。raw '[' ']' 会让 curl 直接 rc=3 (URL malformed)
           + urllib.parse.quote(q + " AND " + DATE, safe="")
           + f"&start=0&max_results={n}&sortBy=submittedDate&sortOrder=descending")
    # 本机 Python ssl/urllib 被对端直接断连（Remote end closed connection）；
    # curl 走 schannel 正常 ⇒ 统一用 curl 取，失败重试 3 次。
    import subprocess
    import tempfile
    last = None
    for attempt in range(3):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xml")
        tmp.close()
        r = subprocess.run(["curl", "-sL", "-m", "90", "--ssl-no-revoke", "-A", "Mozilla/5.0",
                            url, "-o", tmp.name], capture_output=True)
        data = b""
        try:
            data = open(tmp.name, "rb").read()
        except Exception as ex:
            last = ex
        if r.returncode == 0 and b"<entry" in data:
            return data
        last = f"rc={r.returncode} bytes={len(data)}"
        time.sleep(4 + attempt * 4)
    raise RuntimeError(f"curl 取数失败 {last}")


def parse(xml):
    out = []
    root = ET.fromstring(xml)
    for e in root.findall("a:entry", NS):
        aid = e.find("a:id", NS).text.split("/abs/")[-1]
        out.append({
            "id": aid,
            "title": re.sub(r"\s+", " ", e.find("a:title", NS).text).strip(),
            "published": e.find("a:published", NS).text,
            "updated": e.find("a:updated", NS).text,
            "authors": [x.find("a:name", NS).text for x in e.findall("a:author", NS)],
            "cats": [c.get("term") for c in e.findall("a:category", NS)],
            "abs": re.sub(r"\s+", " ", e.find("a:summary", NS).text).strip(),
        })
    return out


def main():
    db = {}
    fail = []
    for name, kw in BUCKETS:
        q = f"({kw}) AND (cat:cs.CL OR cat:cs.AI OR cat:cs.LG OR cat:cond-mat.mtrl-sci OR cat:physics.comp-ph)"
        try:
            ents = parse(fetch(q))
        except Exception as ex:
            fail.append(f"{name}: {type(ex).__name__} {ex}")
            ents = []
        for x in ents:
            rec = db.setdefault(x["id"], dict(x, buckets=[]))
            if name not in rec["buckets"]:
                rec["buckets"].append(name)
        print(f"{name:10s} {len(ents):4d} (total {len(db)})")
        time.sleep(3)

    json.dump({"papers": list(db.values()), "fail": fail}, open("D:/hermes/analysis/_week_papers.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("total", len(db), "fail", fail)


main()
