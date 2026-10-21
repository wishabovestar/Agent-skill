# -*- coding: utf-8 -*-
"""Housekeeping audit dims 10-12, 2026-09-28"""
import os, re, json, sys, hashlib
from collections import defaultdict, Counter

PROF = r"D:\hermes\hermes-data\profiles\mybot"
MEM = os.path.join(PROF, "memories", "MEMORY.md")
USR = os.path.join(PROF, "memories", "USER.md")
SKILLS = os.path.join(PROF, "skills")
USAGE = os.path.join(SKILLS, ".usage.json")
ARCHIVE = os.path.join(SKILLS, ".archive")
SRC = r"C:\Users\Administrator\.agents\skills"

def rd(p):
    try:
        return open(p, encoding="utf-8").read()
    except Exception:
        return ""

print("=" * 70)
print("DIM10 MEMORY SPACE")
print("=" * 70)
m = rd(MEM); u = rd(USR)
# strip comments? memory usage counts chars incl whitespace
print("MEMORY.md bytes=%d chars=%d" % (len(m.encode('utf-8')), len(m)))
print("USER.md   bytes=%d chars=%d" % (len(u.encode('utf-8')), len(u)))
print("MEMORY pct (of 2200) = %.1f%%" % (len(m) / 2200 * 100))
print("USER   pct (of 1375) = %.1f%%" % (len(u) / 1375 * 100))

# blocks split by lines starting with ## or blank-line groups; approximate by "## "
mblocks = [b.strip() for b in re.split(r"\n\s*\n", m) if b.strip()]
print("MEMORY blocks=%d" % len(mblocks))
def toks(s):
    return set(re.findall(r"[A-Za-z0-9_.:/\\-]+|[\u4e00-\u9fff]{2,}", s.lower()))
# jaccard within memory
dups = []
for i in range(len(mblocks)):
    for j in range(i + 1, len(mblocks)):
        a, b = toks(mblocks[i]), toks(mblocks[j])
        if not a or not b: continue
        jac = len(a & b) / len(a | b)
        if jac >= 0.5:
            dups.append((i, j, jac))
print("Intra-MEMORY near-dup pairs (Jaccard>=0.5):", len(dups))
for i, j, jc in dups[:10]:
    print("  [%d]<->[%d] %.2f :: %s | %s" % (i, j, jc, mblocks[i][:40], mblocks[j][:40]))
# cross region
ma, ua = toks(m), toks(u)
print("Cross MEMORY<->USER Jaccard = %.3f  (mem_tok=%d usr_tok=%d)" % (len(ma & ua) / max(1, len(ma | ua)), len(ma), len(ua)))

print()
print("=" * 70)
print("DIM11 SKILL LIBRARY")
print("=" * 70)
# walk for SKILL.md
skill_files = []
for root, dirs, files in os.walk(SKILLS):
    if ".archive" in root.split(os.sep):
        continue
    if "SKILL.md" in files:
        skill_files.append(os.path.join(root, "SKILL.md"))
print("Active SKILL.md files (excl .archive) =", len(skill_files))

def fm(text):
    name = None; desc = None; ver = None
    mm = re.search(r"^---\s*\n(.*?)\n---", text, re.S)
    if mm:
        body = mm.group(1)
        n = re.search(r"^name:\s*(.+)$", body, re.M)
        d = re.search(r"^description:\s*(.+)$", body, re.M)
        v = re.search(r"^version:\s*(.+)$", body, re.M)
        if n: name = n.group(1).strip().strip('"\'')
        if d: desc = d.group(1).strip().strip('"\'')
        if v: ver = v.group(1).strip().strip('"\'')
    return name, desc, ver

names = Counter(); descs = {}
for sf in skill_files:
    t = rd(sf)
    n, d, v = fm(t)
    if n:
        names[n] += 1
        descs.setdefault(n, d or "")
dupn = {k: c for k, c in names.items() if c > 1}
print("Unique frontmatter names =", len(names), " (files=%d)" % len(skill_files))
print("Duplicate prompt names (same name >1 file):", len(dupn))
for k, c in sorted(dupn.items(), key=lambda x: -x[1]):
    print("   %s x%d" % (k, c))
# prompt snapshot cost
total_name_desc = sum(len(k) + len(v or "") for k, v in descs.items())
print("Sum(name+desc) chars =", total_name_desc, "~ tokens", total_name_desc // 4)

# usage
try:
    us = json.load(open(USAGE, encoding="utf-8"))
except Exception as e:
    us = {}
    print("usage load fail", e)
print("usage entries =", len(us))
zero = [k for k, v in us.items() if isinstance(v, dict) and v.get("use_count", 0) == 0]
print("zero-use =", len(zero))
states = Counter(v.get("state") for v in us.values() if isinstance(v, dict))
print("states =", dict(states))
pinned = [k for k, v in us.items() if isinstance(v, dict) and v.get("pinned")]
print("pinned =", len(pinned), pinned)

from datetime import datetime, timezone
now = datetime.now(timezone.utc)
def age_days(ts):
    if not ts: return None
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if t.tzinfo is None: t = t.replace(tzinfo=timezone.utc)
        return (now - t).days
    except Exception:
        return None

stale90 = []; stale30 = []
for k, v in us.items():
    if not isinstance(v, dict): continue
    a = age_days(v.get("last_used_at"))
    if a is None: continue
    if a > 90: stale90.append((k, a))
    elif a > 30: stale30.append((k, a))
print("unused >90d (dead candidates) =", len(stale90))
for k, a in sorted(stale90, key=lambda x: -x[1])[:15]:
    print("   %s  %dd" % (k, a))
print("unused 30-90d =", len(stale30))

# archived count
arch = [d for d in os.listdir(ARCHIVE) if os.path.isdir(os.path.join(ARCHIVE, d))] if os.path.isdir(ARCHIVE) else []
print(".archive dirs =", len(arch))

# broken refs: active skills referencing archived skill names
archnames = set()
for d in arch:
    base = re.split(r"[-.]\d{8}|\.bak", d)[0]
    archnames.add(base)
print("archived skill-name bases =", len(archnames))
refpat = re.compile(r"`([a-z0-9][a-z0-9\-]{3,})`")
broken = Counter()
for sf in skill_files:
    t = rd(sf)
    for m2 in refpat.findall(t):
        if m2 in archnames:
            broken[m2] += 1
print("references to archived names (count) =", sum(broken.values()))
for k, c in broken.most_common(15):
    print("   %s x%d" % (k, c))

# .bak / -dup dirs anywhere under skills and src
bakdirs = []
for base in (SKILLS, SRC):
    for root, dirs, files in os.walk(base):
        for d in list(dirs):
            if d.endswith(".bak") or "-dup" in d or ".bak-" in d:
                bakdirs.append(os.path.join(root, d))
print(".bak/-dup dirs =", len(bakdirs))
for b in bakdirs[:20]:
    print("   ", b)

print()
print("=" * 70)
print("DIM11b MATT POCOCK / SRC")
print("=" * 70)
srcskills = [d for d in os.listdir(SRC) if os.path.isdir(os.path.join(SRC, d)) and not d.startswith(".")]
print("src skills (non-archive) =", len(srcskills))
# overlap src vs profile by frontmatter name
srcnames = set()
for d in srcskills:
    p = os.path.join(SRC, d, "SKILL.md")
    if os.path.exists(p):
        n, _, _ = fm(rd(p))
        if n: srcnames.add(n)
print("src unique names =", len(srcnames))
inter = srcnames & set(names.keys())
print("overlap src <-> profile names =", len(inter))
