import os, re, json

BASE = r"D:/hermes/hermes-data/profiles/mybot/skills"
# find broken references/*.md inside SKILL.md files
pat = re.compile(r'`?(references[/\\][A-Za-z0-9_\-./\\]+\.md)`?')
missing = []
total_refs = 0
for dirpath, dirnames, filenames in os.walk(BASE):
    if '.archive' in dirpath: continue
    for fn in filenames:
        if not fn.endswith('.md'): continue
        p = os.path.join(dirpath, fn)
        try:
            s = open(p, encoding='utf-8', errors='ignore').read()
        except Exception: continue
        for m in pat.findall(s):
            total_refs += 1
            ref = m.replace('\\','/')
            cand = os.path.join(dirpath, *ref.split('/'))
            if not os.path.exists(cand):
                rel = os.path.relpath(p, BASE).replace('\\','/')
                missing.append((rel, ref))

print("total references/ file links:", total_refs)
print("BROKEN references:", len(missing))
from collections import Counter
c = Counter(r for _,r in missing)
for ref, n in c.most_common(40):
    files = sorted({f for f,r in missing if r==ref})
    print(f"  MISSING {ref}  (referenced by {len(files)}): {files[:3]}")

# also check skills_list-level: frontmatter name vs dir name mismatch
mismatch = []
for dirpath, dirnames, filenames in os.walk(BASE):
    if '.archive' in dirpath: continue
    if 'SKILL.md' in filenames:
        p = os.path.join(dirpath,'SKILL.md')
        s = open(p, encoding='utf-8', errors='ignore').read()
        m = re.search(r'^name:\s*(.+)$', s, re.M)
        if m:
            nm = m.group(1).strip().strip('"\'')
            leaf = os.path.basename(dirpath)
            if nm != leaf:
                mismatch.append((os.path.relpath(dirpath,BASE).replace('\\','/'), nm, leaf))
print("\nfrontmatter name != dir leaf:", len(mismatch))
for a,b,c2 in mismatch[:25]:
    print(f"  {a}: name={b} leaf={c2}")
