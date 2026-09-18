#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_horizon_schedule.py — 把 Horizon 每日简报提前到 06:10(修调度顺序死锁)

★ 问题(r1194):
    Horizon 摘要在 08:30 生成(cron 92c2c8149fdb "30 8 * * *"),
    而下游两个消费方都更早:
      06:20  巡天新闻采集(38ec545b3b1c)  ← 读 horizon-{today}-en.md 作兜底源
      08:05  每日新闻早报(f2d76497a282)
    ⇒ ★★ 两个下游【永远】拿不到【当天】的摘要 ⇒ 采集恒为 status=partial。
    🟢 实测证据:horizon-2026-09-18-en.md mtime=08:32;采集在 06:20/08:06。

★ 修法: 把 Horizon 提前到 06:10 —— 它是下游的【输入】, 理应最早生成。
    一条改动同时修好两个下游, 且【不动】用户已习惯的 06:20 / 08:05 时刻。

★ 幂等: 已是目标表达式则跳过。备份写 .bak_r1194
"""
import io
import json
import os
import shutil
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
JOBS = r"D:\hermes\hermes-data\profiles\qqbot3\cron\jobs.json"
JID = "92c2c8149fdb"
OLD_EXPR = "30 8 * * *"
NEW_EXPR = "10 6 * * *"

d = json.load(io.open(JOBS, encoding="utf-8"))
jobs = d.get("jobs", d)
if isinstance(jobs, dict):
    j = jobs.get(JID)
else:
    j = next((x for x in jobs if x.get("id") == JID), None)
if not j:
    print("  🔴 未找到 job %s" % JID)
    sys.exit(1)

cur = (j.get("schedule") or {}).get("expr")
print("  目标: %s (%s)" % (JID, j.get("name", "")[:30]))
print("  当前 expr: %s" % cur)

if cur == NEW_EXPR:
    print("  ⏭ 已是 %s, 跳过" % NEW_EXPR)
    sys.exit(0)

shutil.copy2(JOBS, JOBS + ".bak_r1194_%s" % time.strftime("%Y%m%d_%H%M%S"))
print("  ✅ 已备份 jobs.json")

j.setdefault("schedule", {})
j["schedule"]["expr"] = NEW_EXPR
if "display" in j["schedule"]:
    j["schedule"]["display"] = NEW_EXPR
j["schedule_display"] = NEW_EXPR

io.open(JOBS, "w", encoding="utf-8", newline="\n").write(
    json.dumps(d, ensure_ascii=False, indent=2))

# 复核
d2 = json.load(io.open(JOBS, encoding="utf-8"))
j2 = (d2.get("jobs", d2) or {}).get(JID) if isinstance(d2.get("jobs", d2), dict) \
    else next((x for x in d2.get("jobs", []) if x.get("id") == JID), None)
print("  ★ 复核后 expr: %s" % ((j2 or {}).get("schedule") or {}).get("expr"))
print("  ★ job 总数(应不变): %d" % len(d2.get("jobs", d2)))
