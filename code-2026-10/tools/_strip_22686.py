import re, html, sys, io

src = sys.argv[1]
dst = sys.argv[2]

with io.open(src, 'r', encoding='utf-8', errors='ignore') as f:
    s = f.read()

# keep math alttext as inline text
s = re.sub(r'<math[^>]*alttext="([^"]*)"[^>]*>.*?</math>', lambda m: ' $'+html.unescape(m.group(1))+'$ ', s, flags=re.S)
# drop script/style
s = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', s, flags=re.S|re.I)
# table rows / cells -> separators
s = re.sub(r'</t[dh]>', ' | ', s, flags=re.I)
s = re.sub(r'</tr>', '\n', s, flags=re.I)
# block level tags -> newlines
s = re.sub(r'</(p|div|section|h1|h2|h3|h4|h5|h6|li|figcaption|caption|table|blockquote|dd|dt)>', '\n', s, flags=re.I)
s = re.sub(r'<br\s*/?>', '\n', s, flags=re.I)
# remove all remaining tags
s = re.sub(r'<[^>]+>', ' ', s)
s = html.unescape(s)
# whitespace tidy
s = s.replace('\u00a0', ' ')
s = re.sub(r'[ \t]+', ' ', s)
s = re.sub(r' *\n *', '\n', s)
s = re.sub(r'\n{3,}', '\n\n', s)

lines = [l.rstrip() for l in s.split('\n')]
lines = [l for l in lines if l.strip()]
out = '\n'.join(lines)

with io.open(dst, 'w', encoding='utf-8') as f:
    f.write(out)

print('lines=%d chars=%d' % (len(lines), len(out)))
