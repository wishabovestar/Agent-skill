# -*- coding: utf-8 -*-
"""汇总睡眠巩固 / 白日梦引擎最近运行：读各日 JSON 与目录时间戳。"""
import glob
import json
import os

OUT = r"D:/hermes/hermes-data/profiles/mybot/cron/output"
L = []


def w(s=""):
    L.append(str(s))


for name, pat in (("SLEEP", os.path.join(OUT, "sleep_consolidation_*.json")),
                  ("DREAM", os.path.join(OUT, "daydream_v4_*.json"))):
    fs = sorted(glob.glob(pat))
    w(f"===== {name}  files={len(fs)}")
    for f in fs[-16:]:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception as e:
            w(f"{os.path.basename(f)}  PARSE-FAIL {e}")
            continue
        keys = list(d.keys())
        w(f"{os.path.basename(f)}  keys={keys}")
        for k in ("status", "ts", "generated_at", "findings", "suggestions",
                  "counts", "summary", "replayed", "abstracts", "cross", "stats"):
            if k in d:
                v = d[k]
                if isinstance(v, list):
                    w(f"    {k}: list[{len(v)}]")
                elif isinstance(v, dict):
                    w(f"    {k}: {json.dumps(v, ensure_ascii=False)[:300]}")
                else:
                    w(f"    {k}: {v}")
    w()

# 最近 8 天两 job 的 md 报告大小/时间（看是否有空跑）
for jid, label in (("9cf4ccfdb97b", "sleep"), ("b8d858f17f64", "dream")):
    w(f"===== {label} md 报告 最近 10")
    for f in sorted(glob.glob(os.path.join(OUT, jid, "*.md")))[-10:]:
        st = os.stat(f)
        w(f"  {os.path.basename(f)}  {st.st_size} B")
    w()

open(r"D:/hermes/analysis/_dream_sleep_status.txt", "w", encoding="utf-8").write("\n".join(L))
print("written", len(L), "lines")
