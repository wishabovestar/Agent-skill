# -*- coding: utf-8 -*-
import os, re, json, hashlib
from collections import Counter, defaultdict
SK = r"D:\hermes\hermes-data\profiles\mybot\skills"
MEMD = r"D:\hermes\hermes-data\profiles\mybot\memories"
def rd(p):
    try: return open(p,encoding="utf-8").read()
    except Exception: return ""
def h(p):
    try: return hashlib.sha256(open(p,"rb").read()).hexdigest()[:16]
    except Exception: return "ERR"

print("=== dup-name files ===")
for target in ("computer-use","codebase-inspection"):
    for root,dirs,fs in os.walk(SK):
        if ".archive" in root.split(os.sep): continue
        if "SKILL.md" in fs:
            t=rd(os.path.join(root,"SKILL.md"))
            m=re.search(r"^name:\s*(.+)$",t,re.M)
            if m and m.group(1).strip().strip('"\'')==target:
                dm=re.search(r"^description:\s*(.+)$",t,re.M)
                print("  %-9s | %s" % (target, root))
                print("            desc: %s" % ((dm.group(1).strip()[:110] if dm else ""))) 

print()
print("=== MEMORY backups exact-dup check ===")
seen=defaultdict(list)
for f in os.listdir(MEMD):
    if f.startswith("MEMORY.md.bak") or f.startswith("USER.md"):
        p=os.path.join(MEMD,f)
        if os.path.isfile(p):
            seen[h(p)].append(f)
for hh,files in seen.items():
    if len(files)>1:
        print("  DUP %s -> %s" % (hh, files))
    else:
        print("  %s  %s" % (hh, files[0]))

print()
print("=== active-only zero-use / stale ===")
us=json.load(open(os.path.join(SK,".usage.json"),encoding="utf-8"))
zero=[]; stale=[]; arch=[]
for k,v in us.items():
    if not isinstance(v,dict): continue
    st=v.get("state")
    if st=="archived": arch.append(k); continue
    if v.get("use_count",0)==0: zero.append((k,st))
    elif st=="stale": stale.append((k,v.get("use_count")))
print("archived=%d  zero-use(active/stale)=%d  stale(w/ use)=%d" % (len(arch),len(zero),len(stale)))
print("zero-use names:", sorted(k for k,_ in zero))

print()
print("=== data-privacy (T1) status ===")
found=[]
for base in (SK, r"C:\Users\Administrator\.agents\skills"):
    for root,dirs,fs in os.walk(base):
        if "data-privacy" in root:
            found.append(root)
print("data-privacy dirs:", found)
print("in .archive?", os.path.exists(os.path.join(SK,".archive","data-privacy")))

print()
print("=== prompt snapshot cost ===")
snap=os.path.join(r"D:\hermes\hermes-data\profiles\mybot",".skills_prompt_snapshot.json")
d=json.load(open(snap,encoding="utf-8"))
mani=d.get("manifest",{})
print("snapshot version=%s manifest entries=%d" % (d.get("version"), len(mani)))
# look for content/body size
print("snapshot keys:", list(d.keys()))
for k,v in d.items():
    if k!="manifest":
        s=json.dumps(v)
        print("   %s: %d bytes" % (k, len(s)))

print()
print("=== active skills referencing archived names (full scan) ===")
ARCH=os.path.join(SK,".archive")
archnames=set()
for dd in os.listdir(ARCH):
    base=re.split(r"[-.]\d{8}|\.bak",dd)[0]
    archnames.add(base)
allmd=[]
for root,dirs,fs in os.walk(SK):
    if ".archive" in root.split(os.sep): continue
    for f in fs:
        if f.endswith(".md"): allmd.append(os.path.join(root,f))
refc=Counter()
for p in allmd:
    t=rd(p)
    for m in re.findall(r"`([a-z0-9][a-z0-9\-]{3,})`",t):
        if m in archnames: refc[m]+=1
print("total refs=%d unique-targets=%d files-scanned=%d" % (sum(refc.values()), len(refc), len(allmd)))
for k,c in refc.most_common(25): print("   %-32s x%d" % (k,c))
