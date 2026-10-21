# -*- coding: utf-8 -*-
import json
P=r"D:\hermes\hermes-data\profiles\mybot\cron\jobs.json"
d=json.load(open(P,encoding="utf-8"))
jobs=d["jobs"]
print("jobs key type:", type(jobs).__name__)
items=list(jobs.values()) if isinstance(jobs,dict) else jobs
for j in items:
    n=j.get("name","")
    if "论文" in n or "push" in n.lower():
        print("="*60)
        for k in ("id","name","enabled","schedule_display","no_agent","script","deliver","origin",
                  "model","provider","last_status","last_run_at","last_delivery_error","failure_streak",
                  "skills","skill","prompt"):
            v=j.get(k)
            if v is not None:
                s=str(v)
                print("  %-20s %s" % (k, s[:200]))
print()
print("=== delivery errors across all jobs ===")
for j in items:
    e=j.get("last_delivery_error")
    if e:
        print("  %-30s | %s | %s" % (j.get("name","")[:30], j.get("origin"), str(e)[:120]))
print()
print("=== origin values ===")
from collections import Counter
print(Counter(str(j.get("origin")) for j in items))
print()
print("=== schedules of 论文 jobs vs others sharing time ===")
for j in items:
    print("  %-30s %-14s %s" % (j.get("name","")[:30], j.get("schedule_display"), str(j.get("origin"))[:40]))
