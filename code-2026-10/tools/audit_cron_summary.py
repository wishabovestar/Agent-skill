import json, os, datetime

base = r"D:/hermes/hermes-data/profiles/mybot"
jobs = json.load(open(os.path.join(base, "cron/jobs.json"), encoding="utf-8"))["jobs"]
print(f"TOTAL cron jobs: {len(jobs)}")
print()
for j in jobs:
    sched = j.get("schedule_display") or (j.get("schedule") or {}).get("display")
    print(f"--- [{j.get('id')}] {j.get('name')}")
    print(f"    schedule={sched} enabled={j.get('enabled')} state={j.get('state')}")
    print(f"    model={j.get('model')}/{j.get('provider')} no_agent={j.get('no_agent')}")
    print(f"    script={j.get('script')}")
    print(f"    skills={j.get('skills')}")
    print(f"    last_status={j.get('last_status')} last_run={j.get('last_run_at')}")
    if j.get('last_error'): print(f"    last_error={j.get('last_error')}")
    if j.get('last_delivery_error'): print(f"    last_delivery_error={j.get('last_delivery_error')}")
    if j.get('paused_reason'): print(f"    paused_reason={j.get('paused_reason')}")
