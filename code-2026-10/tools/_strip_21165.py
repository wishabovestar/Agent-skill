import re, html, io

src = r"D:/hermes/analysis/_p0_2610.21165.html"
dst = r"D:/hermes/analysis/_p0_2610.21165.txt"

with io.open(src, "r", encoding="utf-8", errors="ignore") as f:
    s = f.read()

s = re.sub(r"(?is)<script.*?</script>", " ", s)
s = re.sub(r"(?is)<style.*?</style>", " ", s)
s = re.sub(r"(?is)<nav.*?</nav>", " ", s)
s = re.sub(r"(?is)<footer.*?</footer>", " ", s)

s = re.sub(r"(?i)<br\s*/?>", "\n", s)
s = re.sub(r"(?i)</(p|div|h[1-6]|li|tr|section|table|figcaption|blockquote|dt|dd)>", "\n", s)
s = re.sub(r"(?s)<[^>]+>", " ", s)
s = html.unescape(s)
s = re.sub(r"[ \t\u00a0]+", " ", s)
s = re.sub(r"\n\s*\n+", "\n\n", s)
s = "\n".join(l.strip() for l in s.split("\n"))
s = re.sub(r"\n{3,}", "\n\n", s)

with io.open(dst, "w", encoding="utf-8") as f:
    f.write(s)

print("chars", len(s))
print("lines", s.count("\n"))
