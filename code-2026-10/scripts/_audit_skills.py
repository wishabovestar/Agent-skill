import json, os, sys, datetime, re

BASE = r"D:/hermes/hermes-data/profiles/mybot"
usage_path = os.path.join(BASE, "skills", ".usage.json")
data = json.load(open(usage_path, encoding="utf-8"))

now = datetime.datetime.now(datetime.timezone.utc)
print("NOW(UTC):", now.isoformat())
print("TOTAL entries in .usage.json:", len(data))

def parse(t):
    if not t: return None
    try:
        t = t.replace("Z","+00:00")
        return datetime.datetime.fromisoformat(t)
    except Exception:
        return None

active, archived = [], []
for name, rec in data.items():
    if rec.get("state") == "archived" or rec.get("archived_at"):
        archived.append(name)
    else:
        active.append(name)

print("active:", len(active), " archived:", len(archived))

# Dead skills: last_used_at older than 90 days OR never used
DEAD_DAYS = 90
dead, stale, never = [], [], []
for name, rec in data.items():
    lu = parse(rec.get("last_used_at"))
    uc = rec.get("use_count", 0) or 0
    if rec.get("state")=="archived": continue
    if lu is None:
        if uc == 0:
            never.append(name)
        continue
    age = (now - lu).days
    if age > DEAD_DAYS:
        dead.append((name, age, uc))
    elif age > 30:
        stale.append((name, age, uc))

dead.sort(key=lambda x:-x[1]); stale.sort(key=lambda x:-x[1])
print("\n=== DEAD (active but >90d unused): %d ===" % len(dead))
for n,a,u in dead: print(f"  {n:45s} {a:>4d}d  uses={u}")
print("\n=== STALE (31-90d): %d ===" % len(stale))
for n,a,u in stale: print(f"  {n:45s} {a:>4d}d  uses={u}")
print("\n=== NEVER USED (use_count=0) ===")
for n in never: print("  ", n)

# Loaded in last 7 days
recent = []
for name, rec in data.items():
    lu = parse(rec.get("last_used_at"))
    if lu and (now-lu).days <= 7:
        recent.append((name,(now-lu).days,rec.get("use_count",0)))
recent.sort()
print("\n=== USED in last 7d: %d ===" % len(recent))
for n,d,u in recent: print(f"  {n:45s} {d:>2d}d ago uses={u}")

# Directory listing of skills
sd = os.path.join(BASE,"skills")
dirs = sorted([d for d in os.listdir(sd) if os.path.isdir(os.path.join(sd,d)) and not d.startswith('.')])
print("\n=== skills/ dirs: %d ===" % len(dirs))
for d in dirs:
    p = os.path.join(sd,d)
    sym = "LINK" if os.path.islink(p) else "dir "
    has_skill_md = os.path.exists(os.path.join(p,"SKILL.md"))
    inuse = "USAGE" if d in data else "NOUSAGE"
    print(f"  [{sym}][{inuse}] {d}  SKILL.md={has_skill_md}")

# dirs present but not in usage
missing = [d for d in dirs if d not in data]
print("\n=== on disk but NOT in .usage.json: %d ===" % len(missing))
for d in missing: print("  ", d)
