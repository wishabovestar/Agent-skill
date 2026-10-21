# -*- coding: utf-8 -*-
"""Slim card-feeds: meta + headings + captions + numeric sentences (no body tail).
Also builds the Hippo (2610.24453) feed from pdftotext output since arXiv has no HTML v1."""
import io, os, re

BASE = r"D:/hermes/analysis/_rd"
IDS = ["2610.24723", "2610.24671", "2610.24255", "2608.07958", "2607.11521"]

def slim(pid):
    p = os.path.join(BASE, "d_%s.txt" % pid)
    txt = io.open(p, "r", encoding="utf-8", errors="replace").read()
    parts = txt.split("--- BODY TEXT")
    head = parts[0]
    out = os.path.join(BASE, "s_%s.txt" % pid)
    io.open(out, "w", encoding="utf-8", newline="\n").write(head.rstrip() + "\n")
    return len(head)

def hippo():
    abs_p = os.path.join(BASE, "abs_2610.24453.html")
    raw = io.open(abs_p, "r", encoding="utf-8", errors="replace").read()
    import html as ihtml
    TAG = re.compile(r"<[^>]+>")
    def detag(s):
        s = TAG.sub(" ", s)
        s = ihtml.unescape(s)
        return re.sub(r"\s+", " ", s).strip()
    def m1(pat, src=raw, grp=1):
        m = re.search(pat, src, re.S)
        return detag(m.group(grp)) if m else "NOT_FOUND"
    title = m1(r'<meta\s+name="citation_title"\s+content="([^"]*)"')
    aus = [ihtml.unescape(x) for x in re.findall(r'<meta\s+name="citation_author"\s+content="([^"]*)"', raw)]
    date = m1(r'<meta\s+name="citation_date"\s+content="([^"]*)"')
    comments = m1(r'<td class="tablecell comments[^"]*">(.*?)</td>')
    subjects = m1(r'<td class="tablecell subjects">(.*?)</td>')
    abstract = m1(r'<blockquote class="abstract[^"]*">(.*?)</blockquote>')
    body = io.open(os.path.join(BASE, "pdf_2610.24453.txt"), "r", encoding="utf-8", errors="replace").read()
    lines = [l.rstrip() for l in body.split("\n")]
    # section headings: numbered short lines
    heads = []
    for i, l in enumerate(lines):
        s = re.sub(r"\s+", " ", l).strip()
        if 3 < len(s) < 90 and re.match(r"^(\d{1,2}(\.\d{1,2})*|[A-Z]\.)\s+[A-Z]", s):
            heads.append("[h] " + s)
    caps = []
    for i, l in enumerate(lines):
        s = re.sub(r"\s+", " ", l).strip()
        if re.match(r"^(Figure|Table|Fig\.)\s*\d+", s):
            buf = [s]
            for k in range(1, 4):
                if i + k < len(lines):
                    nxt = re.sub(r"\s+", " ", lines[i + k]).strip()
                    if nxt and not re.match(r"^(Figure|Table|Fig\.)\s*\d+", nxt):
                        buf.append(nxt)
            caps.append(" ".join(buf)[:900])
    nums = []
    for l in lines:
        s = re.sub(r"\s+", " ", l).strip()
        if len(s) > 40 and len(re.findall(r"\d", s)) >= 2:
            nums.append("- " + s)
    L = []
    L.append("=" * 78)
    L.append("ID 2610.24453")
    L.append("SOURCE pdf_2610.24453.txt (arXiv html v1 = 404; ar5iv = 307 back to abs)")
    L.append("TITLE %s" % title)
    L.append("AUTHORS %s" % "; ".join(aus))
    L.append("AUTHOR_COUNT %d" % len(aus))
    L.append("DATE %s" % date)
    L.append("COMMENTS %s" % comments)
    L.append("SUBJECTS %s" % subjects)
    L.append("ABSTRACT %s" % abstract)
    L.append("")
    L.append("--- HEADINGS (%d) ---" % len(heads))
    L.extend(heads)
    L.append("")
    L.append("--- CAPTIONS (%d) ---" % len(caps))
    L.extend(["* " + c for c in caps])
    L.append("")
    L.append("--- NUMERIC SENTENCES (%d) ---" % len(nums))
    L.extend(nums)
    out = "\n".join(L) + "\n"
    p = os.path.join(BASE, "s_2610.24453.txt")
    io.open(p, "w", encoding="utf-8", newline="\n").write(out)
    return len(out), len(heads), len(caps), len(nums)

for pid in IDS:
    n = slim(pid)
    print("%-11s slim_chars=%d" % (pid, n))
n, h, c, u = hippo()
print("%-11s slim_chars=%d heads=%d caps=%d nums=%d (from PDF)" % ("2610.24453", n, h, c, u))
