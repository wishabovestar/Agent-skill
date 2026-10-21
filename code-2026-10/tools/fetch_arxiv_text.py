#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取 arXiv 论文元数据 + 正文（HTML 优先、多后端回退、编码探测），落盘为纯文本备深读。

用法:  python fetch_arxiv_text.py 2610.12668v1
输出:  papers/<id>.meta.json   元数据（标题/作者/分类/摘要/提交说明）
       papers/<id>.html       原始 HTML（若拿到）
       papers/<id>.txt        去标签正文
       papers/<id>.pdfmeta.txt PDF 抽取回退文本（若用上）
退出码: 0=拿到正文  3=只拿到摘要  4=全失败
纪律: 抓不到就如实报，不编造正文内容。
"""
import os
import re
import gzip
import json
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'papers')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/122.0 Safari/537.36')


def get(url, timeout=120):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/pdf,*/*',
        'Accept-Encoding': 'gzip',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get('Content-Encoding') == 'gzip':
            raw = gzip.decompress(raw)
        return raw


def decode(raw):
    for enc in ('utf-8', 'gbk', 'gb18030', 'latin-1'):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode('utf-8', 'replace')


def strip_html(h):
    h = re.sub(r'(?is)<(script|style|svg|noscript|head)[^>]*>.*?</\1>', ' ', h)
    h = re.sub(r'(?is)</(p|div|li|h[1-6]|tr|section|figure|figcaption|table|blockquote)>', '\n', h)
    h = re.sub(r'(?is)<br\s*/?>', '\n', h)
    h = re.sub(r'(?s)<[^>]+>', ' ', h)
    for a, b in (('&nbsp;', ' '), ('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'),
                 ('&#39;', "'"), ('&quot;', '"'), ('&times;', 'x'), ('&le;', '<='),
                 ('&ge;', '>='), ('&minus;', '-'), ('&rarr;', '->'), ('&#x', 'x')):
        h = h.replace(a, b)
    h = re.sub(r'&#\d+;', ' ', h)
    h = re.sub(r'[ \t\u00a0]+', ' ', h)
    h = re.sub(r'\n[ \t]*', '\n', h)
    h = re.sub(r'\n{3,}', '\n\n', h)
    return h.strip()


def meta_from_api(aid):
    base = aid.split('v')[0]
    url = 'http://export.arxiv.org/api/query?' + urllib.parse.urlencode({'id_list': base})
    root = ET.fromstring(get(url))
    ns = {'a': 'http://www.w3.org/2005/Atom', 'x': 'http://arxiv.org/schemas/atom'}
    e = root.find('a:entry', ns)
    if e is None:
        return {}
    g = lambda p: (e.find(p, ns).text or '').strip().replace('\n', ' ') if e.find(p, ns) is not None else ''
    return {
        'id': base,
        'title': g('a:title'),
        'published': g('a:published')[:10],
        'updated': g('a:updated')[:10],
        'authors': [a.find('a:name', ns).text for a in e.findall('a:author', ns)],
        'categories': [c.get('term') for c in e.findall('a:category', ns)],
        'primary': (e.find('x:primary_category', ns).get('term')
                    if e.find('x:primary_category', ns) is not None else ''),
        'comment': g('x:comment'),
        'journal_ref': g('x:journal_ref'),
        'abstract': g('a:summary'),
    }


def pdf_text(raw):
    try:
        import io as _io
        from pypdf import PdfReader
        rd = PdfReader(_io.BytesIO(raw))
        return '\n'.join((p.extract_text() or '') for p in rd.pages)
    except Exception as ex:
        return f'[pypdf 抽取失败: {ex}]'


def main():
    aid = sys.argv[1] if len(sys.argv) > 1 else '2610.12668v1'
    base = aid.split('v')[0]
    os.makedirs(OUT, exist_ok=True)
    log = []

    meta = {}
    try:
        meta = meta_from_api(aid)
        log.append(f'arXiv API ✓ {meta.get("title","")} | {meta.get("published","")} | '
                   f'{len(meta.get("authors",[]))} 作者 | {meta.get("primary","")}')
    except Exception as ex:
        log.append(f'arXiv API ✗ {ex}')
    with open(os.path.join(OUT, f'{aid}.meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    html_urls = [f'https://arxiv.org/html/{aid}',
                 f'https://arxiv.org/html/{base}',
                 f'https://ar5iv.labs.arxiv.org/html/{base}']
    body = ''
    for u in html_urls:
        try:
            raw = get(u)
            txt = decode(raw)
            if len(txt) < 3000:
                log.append(f'HTML {u} → 过短({len(txt)}B) 跳过')
                continue
            with open(os.path.join(OUT, f'{aid}.html'), 'w', encoding='utf-8') as f:
                f.write(txt)
            body = strip_html(txt)
            log.append(f'HTML ✓ {u} → 原始 {len(txt)} 字符, 正文 {len(body)} 字符')
            break
        except Exception as ex:
            log.append(f'HTML ✗ {u} → {type(ex).__name__}: {ex}')

    if len(body) < 5000:
        for u in [f'https://arxiv.org/pdf/{aid}', f'https://arxiv.org/pdf/{base}']:
            try:
                raw = get(u, timeout=180)
                t = pdf_text(raw)
                if len(t) > 5000:
                    with open(os.path.join(OUT, f'{aid}.pdfmeta.txt'), 'w', encoding='utf-8') as f:
                        f.write(t)
                    body = t
                    log.append(f'PDF ✓ {u} → 抽取 {len(t)} 字符')
                    break
                log.append(f'PDF {u} → 抽取过短({len(t)}) 跳过')
            except Exception as ex:
                log.append(f'PDF ✗ {u} → {type(ex).__name__}: {ex}')

    print('\n'.join(log))
    if len(body) > 5000:
        p = os.path.join(OUT, f'{aid}.txt')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(body)
        print(f'\n正文档: {p}  ({len(body)} 字符)')
        print('--- 头 1,200 字符 ---')
        print(body[:1200])
        return 0
    print('\n⚠️ 未取到正文（只有摘要级别信息）')
    if meta.get('abstract'):
        print('--- 摘要 ---')
        print(meta['abstract'][:2000])
    return 3


if __name__ == '__main__':
    raise SystemExit(main())
