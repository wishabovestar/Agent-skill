# -*- coding: utf-8 -*-
"""核 3 件事：① 两脚本是否有写动作（还是只出报告）② git 快照基线是否可用 ③ 告警是否天天重复"""
import hashlib
import json
import os
import re
import subprocess

P = r"D:/hermes/hermes-data/profiles/mybot/scripts/"
L = []


def w(s=""):
    L.append(str(s))


for fn in ("sleep_consolidation_v2.py", "daydream_engine_v4.py"):
    src = open(P + fn, encoding="utf-8", errors="replace").read()
    w(f"===== {fn}  {len(src.splitlines())} 行")
    for pat in (r"open\([^)]*['\"]w", r"\.write\(", r"INSERT", r"UPDATE ", r"json\.dump\(",
                r"subprocess", r"memory\b", r"skill"):
        hits = re.findall(pat, src)
        w(f"   {pat!r:28s} x{len(hits)}")
    # 是否读自己的历史结果做去重
    w(f"   reads own history: {'prev' in src or 'last_' in src or 'history' in src}")

# git 快照
w()
w("===== memory_git_snapshot 仓库")
gs = open(P + "memory_git_snapshot.py", encoding="utf-8", errors="replace").read()
m = re.search(r"REPO\w*\s*=\s*r?[\"']([^\"']+)", gs) or re.search(r"[\"']([A-Za-z]:[^\"']*memor[^\"']*)[\"']", gs)
w(f"repo hint: {m.group(1) if m else 'not found in source'}")
for cand in (r"D:/hermes/hermes-data/profiles/mybot/memories",
             r"D:/hermes/hermes-data/profiles/mybot/memories/.git",
             r"D:/hermes/memory_git"):
    w(f"  exists {cand}: {os.path.exists(cand)}")

# 告警重复度：最近 6 天 findings 文本指纹
w()
w("===== 睡眠 findings 指纹（最近 8 天）")
import glob
for f in sorted(glob.glob(r"D:/hermes/hermes-data/profiles/mybot/cron/output/sleep_consolidation_2026*.json"))[-8:]:
    d = json.load(open(f, encoding="utf-8"))
    fs = d.get("findings", [])
    fp = hashlib.md5("|".join(str(x) for x in fs).encode()).hexdigest()[:8]
    w(f"  {os.path.basename(f)[-13:-5]}  status={d.get('status'):16s} n={len(fs)}  fp={fp}")

open(r"D:/hermes/analysis/_dream_sleep_core.txt", "w", encoding="utf-8").write("\n".join(L))
print("ok")
