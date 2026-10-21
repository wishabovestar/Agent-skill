import ssl, urllib.request, urllib.parse, json, time, sys, io, os, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
# 2026-10-20 修复：Windows 注册表代理(socks5h://127.0.0.1:10810)会让 urllib 全源 SSL EOF，
# 必须用空 ProxyHandler 强制直连（见 skill 陷阱条目）
OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=ctx),
)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# token lookup (optional)
TOK = None
for p in ['D:/hermes/data/credentials/github_token.txt', 'D:/hermes/data/credentials/github.json']:
    if os.path.exists(p):
        try:
            t = open(p, encoding='utf-8').read().strip()
            if t.startswith('{'):
                TOK = json.loads(t).get('token')
            else:
                TOK = t
            print('TOKEN from', p, 'len', len(TOK or ''))
            break
        except Exception as e:
            print('tok err', e)

def gh(path, tries=2):
    url = 'https://api.github.com' + path
    for i in range(tries):
        try:
            h = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
            if TOK:
                h["Authorization"] = "Bearer " + TOK
            req = urllib.request.Request(url, headers=h)
            with OPENER.open(req, timeout=30) as r:
                return json.loads(r.read().decode('utf-8', 'ignore'))
        except Exception as e:
            print('  ERR', path[:60], type(e).__name__, str(e)[:100])
            time.sleep(4)
    return None

def search(q, sort='stars', per=12):
    p = '/search/repositories?q=' + urllib.parse.quote(q, safe=':+><=') + f'&sort={sort}&order=desc&per_page={per}'
    return gh(p)

QUERIES = [
    ("T1", "anthropic+leak+stars:>50"),
    ("T1", "claude+mythos"),
    ("T1", "oceanus+model+stars:>20"),
    ("T1", "model+weights+leak+stars:>200"),
    ("T1b", "created:>2026-09-01+stars:>3000"),
    ("T1b", "created:>2026-09-10+stars:>800"),
    ("T2", "tata+electronics"),
    ("T2", "apple+supply+chain+stars:>100"),
    ("T2", "create+model+repo+stars:>1"),  # placeholder skip
    ("T3", "apple+openai+lawsuit"),
    ("T3", "created:>2026-09-14+stars:>500"),
]
out = {}
for tag, q in QUERIES:
    if 'placeholder' in q:
        continue
    d = search(q)
    items = (d or {}).get('items') or []
    rows = []
    for i in items:
        rows.append({'full_name': i.get('full_name'), 'stars': i.get('stargazers_count'),
                     'lang': i.get('language'), 'created': (i.get('created_at') or '')[:10],
                     'pushed': (i.get('pushed_at') or '')[:10], 'url': i.get('html_url'),
                     'desc': (i.get('description') or '')[:220],
                     'topics': (i.get('topics') or [])[:6]})
    out[tag + '::' + q] = {'total': (d or {}).get('total_count'), 'rows': rows}
    print(f"[{q}] total={(d or {}).get('total_count')} got={len(rows)}")
    for r in rows[:8]:
        print(f"   {r['full_name']} | {r['stars']} | {r['lang']} | created {r['created']} | {r['desc'][:110]}")
    time.sleep(8)

os.makedirs('D:/hermes/data/intel/logs', exist_ok=True)
json.dump(out, open('D:/hermes/data/intel/logs/_gh_scout_raw.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('SAVED raw')
