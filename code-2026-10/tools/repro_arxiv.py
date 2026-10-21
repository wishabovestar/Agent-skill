#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
repro_arxiv.py — C 类: 源可取回。抽取归档里【有 arXiv 手柄 + 记录过数字】的条目，
逐个去 export.arxiv.org 重取，核对: 作者数 / v1 日期 / 版本数 / 标题。

依据归档自己的铁律: 元数据【必须】从 export.arxiv.org/api/query?id_list=<ID> 直接取。
"""
import os, re, json, sys, time, urllib.request
import xml.etree.ElementTree as ET

BASE = r'D:/hermes/analysis'
ARCH = os.path.join(BASE, 'PAPER_ARCHIVE_agent_memory_swarm_2026-10.md')
NS = {'a': 'http://www.w3.org/2005/Atom'}

def entries(t):
    """切出每个 ### N 条目 ⇒ (编号, 标题行, 正文)"""
    heads = [(m.start(), int(m.group(1))) for m in re.finditer(r'^###\s*#?(\d{1,3})[\.\s:：]', t, re.M)]
    out = []
    for i, (pos, num) in enumerate(heads):
        end = heads[i+1][0] if i+1 < len(heads) else len(t)
        blk = t[pos:end]
        head = [l for l in blk.split('\n') if l.strip()][0]
        out.append((num, head, blk))
    return out

def parse_entry(head, body):
    # ⚠️⚠️ 修(第二轮): 只从【标题行】取 ID 与日期。
    #    否则会把条目里"邻近工作/先驱工作（勿混）"的 ID 当成本篇 ⇒ 全假阳性。
    aid = re.search(r'arXiv[:\s]*(\d{4}\.\d{4,5})', head)
    if not aid: return None
    # 作者数: 仍从头行优先, 再退正文（要求前置字符不是数字/./-/#）
    ac = re.search(r'(?<![\d.\-#])(\d{1,3})\s*(?:位)?\s*作者', head) or \
         re.search(r'(?<![\d.\-#])(\d{1,3})\s*(?:位)?\s*作者', body)
    # v1 日期: 优先标题行的 "(v1 MM-DD/v2 MM-DD)" 形式 → 补全年份；退 "v1 YYYY-MM-DD"
    v1 = None
    m = re.search(r'v1\s+(\d{2})-(\d{2})', head)
    if m:
        yr = re.search(r'arXiv[:\s]*(\d{2})\d{2}\.', head)          # 2608 ⇒ 2026
        v1 = (f'20{yr.group(1)}-{m.group(1)}-{m.group(2)}' if yr else f'????-{m.group(1)}-{m.group(2)}')
    else:
        m = re.search(r'v1[^0-9]{0,6}(\d{4})-(\d{2})-(\d{2})', head) or \
            re.search(r'(\d{4})-(\d{2})-(\d{2})', head)
        v1 = (f'{m.group(1)}-{m.group(2)}-{m.group(3)}' if m else None)
    return dict(arxiv=aid.group(1),
                rec_authors=int(ac.group(1)) if ac else None,
                rec_v1=v1, composite=False)

def fetch(ids):
    url = 'http://export.arxiv.org/api/query?id_list=' + ','.join(ids) + '&max_results=50'
    req = urllib.request.Request(url, headers={'User-Agent': 'repro-audit/1.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode('utf-8', 'replace')

def main():
    t = open(ARCH, encoding='utf-8', errors='replace').read()
    cand = []
    for num, head, body in entries(t):
        p = parse_entry(head, body)
        if p and p['rec_authors']:            # 只挑【记录过作者数】的 ⇒ 有可核对的数字
            p['n'] = num; cand.append(p)
    print(f'归档中【有 arXiv(标题行) + 记录了作者数】的条目: {len(cand)} 个')
    use  = [p for p in cand if not p['composite']]
    skip = [p for p in cand if p['composite']]
    print(f'  ⇒ 可核对 {len(use)} 个；排除复合条目 {len(skip)} 个 {[p["n"] for p in skip]}\n')
    real = {}
    for i in range(0, len(use), 40):
        chunk = use[i:i+40]
        xml = fetch([p['arxiv'] for p in chunk])
        root = ET.fromstring(xml)
        for e in root.findall('a:entry', NS):
            raw = e.find('a:id', NS).text
            aid = re.search(r'(\d{4}\.\d{4,5})', raw).group(1)
            real[aid] = dict(authors=len(e.findall('a:author', NS)),
                             v1=e.find('a:published', NS).text[:10],
                             title=' '.join(e.find('a:title', NS).text.split()))
        time.sleep(1)
    print('=' * 104)
    print(f'  {"#":>4} {"arXiv":<12}{"作者 归档/实取":>16}{"v1 归档/实取":>28}  判决')
    print('=' * 104)
    ok = bad = 0; rows = []
    for p in use:
        r = real.get(p['arxiv'])
        if not r:
            print(f'  {p["n"]:>4} {p["arxiv"]:<12}  ⚠️ API 未返回'); continue
        a_ok = (p['rec_authors'] == r['authors'])
        d_ok = (p['rec_v1'] == r['v1']) if p['rec_v1'] else None
        good = a_ok and (d_ok is not False)
        ok += good; bad += (not good)
        rows.append(dict(n=p['n'], arxiv=p['arxiv'], rec_a=p['rec_authors'], real_a=r['authors'],
                         rec_v1=p['rec_v1'], real_v1=r['v1'], a_ok=a_ok, d_ok=d_ok))
        print(f'  {p["n"]:>4} {p["arxiv"]:<12}{str(p["rec_authors"])+"/"+str(r["authors"]):>16}'
              f'{str(p["rec_v1"])+"/"+r["v1"]:>28}  {"✅" if good else "❌"}'
              + ('' if a_ok else '  ⚠️作者数')
              + ('' if d_ok is not False else '  ⚠️日期'))
    print('─' * 104)
    print(f'  ⭐ 复现 {ok} · 不复现 {bad} · 复现率 {ok/max(1,ok+bad):.0%}')
    json.dump(dict(rows=rows, ok=ok, bad=bad, skipped=[p['n'] for p in skip]),
              open(os.path.join(BASE, 'repro_arxiv.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print('  明细 → repro_arxiv.json')
    return 0

if __name__ == '__main__':
    sys.exit(main())
