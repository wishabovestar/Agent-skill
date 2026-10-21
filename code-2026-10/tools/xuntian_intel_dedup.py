import json, os, sys, io, datetime, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

LOG = 'D:/hermes/data/intel/logs/collection_log.json'
d = json.load(open(LOG, encoding='utf-8'))
print('last_run:', d.get('last_run'))

urls, hashes, titles, keys = set(), set(), set(), set()

def walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            keys.add(k)
            if isinstance(v, str):
                if v.startswith('http'):
                    urls.add(v.rstrip('/').lower())
                elif re.fullmatch(r'[0-9a-f]{8,64}', v):
                    hashes.add(v)
                else:
                    titles.add(v.strip().lower())
            else:
                walk(v)
    elif isinstance(o, list):
        for x in o:
            walk(x)

walk(d.get('entries') or [])
walk(d.get('collections') or [])
print('KEYS USED:', sorted(keys))
print('URLS:', len(urls), 'HASHES:', len(hashes), 'STRINGS:', len(titles))

# add archived filenames as dedup surface
files = []
for p in ['D:/hermes/data/intel/tata_apple', 'D:/hermes/data/intel/anthropic_code',
          'D:/hermes/data/intel', 'D:/hermes/data/intel/logs']:
    if os.path.isdir(p):
        for f in os.listdir(p):
            if f.lower().endswith(('.md', '.json', '.html', '.txt')):
                files.append(f.lower())
print('ARCHIVED FILES:', len(set(files)))

os.makedirs('D:/hermes/data/intel/logs', exist_ok=True)
json.dump({'urls': sorted(urls), 'hashes': sorted(hashes), 'strings': sorted(titles),
           'files': sorted(set(files)), 'ts': datetime.datetime.now().isoformat()},
          open('D:/hermes/data/intel/logs/_seen_index.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print('OK saved index')

# last 5 entries summary
for e in (d.get('entries') or [])[-4:]:
    print('---', e.get('id'), '|', e.get('timestamp'), '| new=', e.get('new_urls'), '| tgt=', e.get('targets'))
