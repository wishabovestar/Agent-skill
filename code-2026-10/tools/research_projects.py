#!/usr/bin/env python3
"""批量研究GitHub项目 — 获取star/描述/更新时间/README摘要"""
import urllib.request, json, time

PROJECTS = [
    'buzz', 'open-skill', 'reverse-skill', 'openwork', 'tailwindcss',
    'I-have-ADHD', 'data-engineer-handbook', 'cloudflare/computer',
    'Pretrained-battery-transformer', 'CMuon', 'diverseDiT++',
    'TextLDM', 'BLT-D', 'UniNav'
]

def api(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'hermes-research', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)

results = {}
for p in PROJECTS:
    try:
        d = api(f'https://api.github.com/search/repositories?q={p}&sort=stars&per_page=3')
        items = d.get('items', [])
        if items:
            results[p] = []
            for i in items[:3]:
                results[p].append({
                    'full_name': i['full_name'],
                    'stars': i['stargazers_count'],
                    'desc': (i.get('description') or '')[:100],
                    'lang': i.get('language'),
                    'updated': i.get('updated_at', '')[:10],
                    'html': i['html_url']
                })
        else:
            results[p] = [{'full_name': 'N/A', 'note': '未找到'}]
    except Exception as e:
        results[p] = [{'full_name': 'ERROR', 'note': str(e)[:60]}]
    time.sleep(0.5)

with open('D:/hermes/data/results/project_batch1.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

for p, items in results.items():
    print(f"\n=== {p} ===")
    for i in items:
        print(f"  {i.get('full_name')} ⭐{i.get('stars','?')} | {i.get('lang','')} | 更新{i.get('updated','')}")
        print(f"    {i.get('desc','')}")
        if i.get('note'): print(f"    ⚠️ {i['note']}")
