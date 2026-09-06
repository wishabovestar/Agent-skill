# -*- coding: utf-8 -*-
"""僵尸 running 检测: 最近 Running 无 completed 的 job"""
import re
from collections import defaultdict
from datetime import datetime

raw = open(r"D:\hermes\hermes-data\profiles\qqbot3\logs\agent.log", encoding="utf-8", errors="ignore").read()
runs = re.findall(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?Running job '([^']+)' \(ID: ([a-f0-9]{12})", raw)
comps = re.findall(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?Job '([^']+)' (?:completed successfully|failed|returned)", raw)
print(f"总 Running: {len(runs)} | 完成标记: {len(comps)}")


def ts(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


last_runs = defaultdict(list)
for t, name, jid in runs:
    last_runs[name].append(ts(t))
comp_set = {}
for t, name in comps:
    comp_set[name] = ts(t)

issues = []
for name, times in last_runs.items():
    t_last = max(times)
    last_comp = comp_set.get(name)
    if last_comp is None or t_last > last_comp:
        age_min = (datetime.now() - t_last).total_seconds() / 60
        issues.append((name, str(t_last)[:19], age_min))

issues.sort(key=lambda x: -x[2])
print("\n=== 最近 Running 但无 completed (卡住/僵尸候选) ===")
for name, t, age in issues[:10]:
    print(f"  {age:.0f}min 前启动未收尾 | {t} | {name[:70]}")
if not issues:
    print("  无 — 全部 job 正常收尾")
