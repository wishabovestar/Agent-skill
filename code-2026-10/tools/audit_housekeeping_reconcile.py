import json, os, sys

os.chdir(r"D:/hermes/hermes-data/profiles/mybot/skills")
data = json.load(open('.usage.json', encoding='utf-8'))
active = {k: v for k, v in data.items() if v.get('state') == 'active'}

# recursive disk scan of skill directories (skip dot dirs)
disk = set()
for root, dirs, files in os.walk('.'):
    parts = [p for p in root.split(os.sep) if p not in ('', '.')]
    if any(p.startswith('.') for p in parts):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        continue
    for d in dirs:
        if d.startswith('.'):
            continue
        rel = os.path.normpath(os.path.join(root, d))
        rel = rel.replace(os.sep, '/')
        if rel.startswith('./'):
            rel = rel[2:]
        disk.add(rel)

disk_flat = set()
for d in disk:
    disk_flat.add(d.split('/')[-1])

def norm_key(k):
    return k.split('/')[-1]

missing = []
for k in active:
    leaf = norm_key(k)
    if k not in disk and leaf not in disk_flat:
        missing.append(k)

print(f'active skills in usage.json: {len(active)}')
print(f'skill dirs on disk (recursive): {len(disk)}')
print(f'GHOST (active in tracker, no dir anywhere): {len(missing)}')
print()
print('=== GHOST skills (tracker entries without disk dir) ===')
for m in sorted(missing):
    print('  ', m)

# never-used that DO exist on disk (real dead candidates)
never_used_on_disk = []
for k, v in active.items():
    if (v.get('use_count') or 0) == 0:
        leaf = norm_key(k)
        if k in disk or leaf in disk_flat:
            never_used_on_disk.append((k, v.get('created_at', '')[:10]))
print()
print(f'=== NEVER USED + ON DISK: {len(never_used_on_disk)} ===')
for k, c in sorted(never_used_on_disk, key=lambda x: x[1]):
    print(f'  {k}  (created {c})')
