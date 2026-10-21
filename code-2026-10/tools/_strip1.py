import re, sys, html
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
s = src.read_text(encoding="utf-8", errors="ignore")
s = re.sub(r"(?is)<(script|style|nav|footer|svg)\b.*?</\1>", " ", s)
s = re.sub(r"(?is)<br\s*/?>", "\n", s)
s = re.sub(r"(?is)</(p|h1|h2|h3|h4|h5|h6|li|tr|div|figcaption|table|section|blockquote)>", "\n", s)
s = re.sub(r"(?is)</t[dh]>", "\t", s)
s = re.sub(r"(?s)<[^>]+>", " ", s)
s = html.unescape(s)
s = s.replace("\u00a0", " ")
lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in s.split("\n")]
lines = [ln for ln in lines if ln]
out = "\n".join(lines)
dst.write_text(out, encoding="utf-8")
print("lines", len(lines), "chars", len(out))
