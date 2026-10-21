# -*- coding: utf-8 -*-
import json, os, re
from collections import Counter
P = r"D:\hermes\hermes-data\profiles\mybot\cron\jobs.json"
d = json.load(open(P, encoding="utf-8"))
print("top-level type:", type(d).__name__)
if isinstance(d, dict):
    print("keys:", list(d.keys())[:10])
    jobs = d.get("jobs", d)
else:
    jobs = d
if isinstance(jobs, dict):
    items = list(jobs.values())
elif isinstance(jobs, list):
    items = jobs
else:
    items = []
print("n jobs =", len(items))
if items:
    print("sample job keys:", sorted(items[0].keys()))
print()
noagent = 0; nomodel = 0; err = 0; ok = 0
missing_script = []
deliv = Counter()
rows = []
for j in items:
    if not isinstance(j, dict): continue
    jid = j.get("id") or j.get("job_id") or "?"
    name = j.get("name") or j.get("title") or "?"
    en = j.get("enabled")
    model = j.get("model")
    na = j.get("no_agent")
    script = j.get("script")
    ls = j.get("last_status")
    lr = j.get("last_run_at")
    dm = j.get("delivery") or j.get("deliver") or j.get("destination") or j.get("platform")
    if na: noagent += 1
    if not model and not na: nomodel += 1
    if ls == "error": err += 1
    elif ls == "ok": ok += 1
    if na and script:
        sp = script
        # resolve
        cand = [sp, os.path.join(r"D:\hermes\hermes-data\profiles\mybot", sp),
                os.path.join(r"D:\hermes\hermes-data\profiles\mybot\scripts", sp),
                os.path.join(r"D:\hermes\analysis", sp)]
        if not any(os.path.exists(c) for c in cand):
            missing_script.append((name, sp))
    deliv[str(dm)] += 1
    rows.append((name, en, "na" if na else "llm", bool(model), ls, lr, str(dm), script))

print("no_agent=%d  llm-without-model=%d  last_status ok=%d err=%d" % (noagent, nomodel, ok, err))
print("missing scripts:", missing_script)
print()
print("delivery targets:", dict(deliv))
print()
print("%-42s %-7s %-4s %-5s %-7s %-20s %s" % ("name", "enabled", "kind", "model", "last", "last_run", "delivery"))
for r in rows:
    print("%-42s %-7s %-4s %-5s %-7s %-20s %s" % (r[0][:42], r[1], r[2], r[3], r[4], str(r[5])[:19], r[6][:40]))
