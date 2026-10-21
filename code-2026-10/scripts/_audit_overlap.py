import os, re, json, itertools

BASE = r"D:/hermes/hermes-data/profiles/mybot/skills"

def walk_skills(root):
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        if '.archive' in dirpath or '.curator_backups' in dirpath or '.hub' in dirpath:
            continue
        if 'SKILL.md' in filenames:
            rel = os.path.relpath(dirpath, root).replace('\\','/')
            out[rel] = os.path.join(dirpath,'SKILL.md')
    return out

skills = walk_skills(BASE)
print("skills with SKILL.md:", len(skills))

STOP = set("the a an and or of to for in on with use using skill skills when this that is are be as at it its from by your you will can should".split())

def tokens(text):
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]{2,}", text.lower())
    return set(w for w in words if w not in STOP)

def desc_of(path):
    try:
        s = open(path, encoding='utf-8', errors='ignore').read()[:3000]
    except Exception:
        return "", ""
    m = re.search(r'name:\s*(.*)', s)
    name = (m.group(1) if m else os.path.basename(os.path.dirname(path))).strip().strip('"\'')
    m = re.search(r'description:\s*(.*)', s)
    desc = m.group(1) if m else ""
    return name, desc

meta = {k: desc_of(v) for k,v in skills.items()}
tok = {k: tokens(v[0]+" "+v[1]) for k,v in meta.items()}

# pairwise jaccard on the LAST path component name + description tokens
pairs = []
items = list(skills.keys())
for a,b in itertools.combinations(items,2):
    ta, tb = tok[a], tok[b]
    if not ta or not tb: continue
    inter = ta & tb
    j = len(inter)/len(ta|tb)
    # also name-token overlap
    na = set(meta[a][0].lower().replace('_','-').split('-'))
    nb = set(meta[b][0].lower().replace('_','-').split('-'))
    nj = (len(na&nb)/len(na|nb)) if (na|nb) else 0
    if j >= 0.6 or nj >= 0.6:
        pairs.append((round(j,3), round(nj,3), a, b))
pairs.sort(reverse=True)
print("\n=== PAIRS with desc-overlap>=0.60 or name-overlap>=0.60: %d ===" % len(pairs))
for j,nj,a,b in pairs:
    print(f"  desc={j:.2f} name={nj:.2f}  {a}  <=>  {b}")

# explicit duplicate-name detection (same leaf name at different paths)
from collections import defaultdict
leaf = defaultdict(list)
for k in skills:
    leaf[os.path.basename(k)].append(k)
print("\n=== SAME LEAF NAME (namespace duplicates) ===")
for n,paths in sorted(leaf.items()):
    if len(paths) > 1:
        print("  ", n, "->", paths)
