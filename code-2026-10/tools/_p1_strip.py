import re, sys, html
src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding='utf-8', errors='replace').read()
s = re.sub(r'(?is)<(script|style|svg|math)[^>]*>.*?</\1>', ' ', s)
s = re.sub(r'(?is)<(p|div|h1|h2|h3|h4|h5|li|tr|br|section|table|figcaption|article|header|span class="ltx_)', r'\n<\1', s)
s = re.sub(r'(?s)<[^>]+>', ' ', s)
s = html.unescape(s)
s = re.sub(r'[ \t\xa0]+', ' ', s)
s = re.sub(r'\n\s*\n\s*\n+', '\n\n', s)
lines = [l.strip() for l in s.split('\n')]
open(dst, 'w', encoding='utf-8').write('\n'.join(l for l in lines if l))
print(dst, 'lines:', sum(1 for _ in open(dst, encoding='utf-8')))
