# -*- coding: utf-8 -*-
"""Per-paper digest: meta(title/authors/date/abstract), H2-H4 headings, table/figure captions,
numeric sentences. Writes _rd/d_<id>.txt and prints verifiable counts."""
import io, os, re, html as ihtml

BASE = r"D:/hermes/analysis/_rd"
IDS = ["2610.24723", "2610.24453", "2610.24671", "2610.24255", "2608.07958", "2607.11521"]
TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"[ \t\xa0]+")
NUM = re.compile(r"\d")

def detag(s):
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</(p|div|li|tr|h1|h2|h3|h4|h5|section|figcaption|caption|td|th)>", "\n", s, flags=re.I)
    s = TAG.sub(" ", s)
    s = ihtml.unescape(s)
    lines = []
    for ln in s.split("\n"):
        ln = WS.sub(" ", ln).strip()
        if ln:
            lines.append(ln)
    return "\n".join(lines)

def meta(abs_html):
    m = {}
    t = re.search(r'<meta\s+name="citation_title"\s+content="([^"]*)"', abs_html)
    m["title"] = ihtml.unescape(t.group(1)) if t else "NOT_FOUND"
    au = re.findall(r'<meta\s+name="citation_author"\s+content="([^"]*)"', abs_html)
    m["authors"] = [ihtml.unescape(x) for x in au]
    d = re.search(r'<meta\s+name="citation_date"\s+content="([^"]*)"', abs_html)
    m["date"] = d.group(1) if d else "NOT_FOUND"
    sub = re.search(r'<div class="dateline">(.*?)</div>', abs_html, re.S)
    m["dateline"] = detag(sub.group(1)) if sub else "NOT_FOUND"
    ab = re.search(r'<blockquote class="abstract[^"]*">(.*?)</blockquote>', abs_html, re.S)
    m["abstract"] = detag(ab.group(1)) if ab else "NOT_FOUND"
    cm = re.search(r'<td class="tablecell comments[^"]*">(.*?)</td>', abs_html, re.S)
    m["comments"] = detag(cm.group(1)) if cm else "NOT_FOUND"
    sub2 = re.search(r'<td class="tablecell subjects">(.*?)</td>', abs_html, re.S)
    m["subjects"] = detag(sub2.group(1)) if sub2 else "NOT_FOUND"
    return m

def skim(html_txt):
    body = html_txt
    i = body.find('<article')
    if i > 0:
        body = body[i:]
    heads = []
    for lvl in ("h2", "h3", "h4"):
        for mm in re.finditer(r"<%s[^>]*>(.*?)</%s>" % (lvl, lvl), body, re.S):
            txt = detag(mm.group(1))
            txt = WS.sub(" ", txt).replace("\n", " ").strip()
            if txt and len(txt) < 220:
                heads.append((lvl, txt))
    caps = []
    for mm in re.finditer(r"<(figcaption|caption)[^>]*>(.*?)</\1>", body, re.S):
        txt = detag(mm.group(2))
        txt = re.sub(r"\s+", " ", txt).strip()
        if txt:
            caps.append(txt)
    text = detag(body)
    nums = []
    for ln in text.split("\n"):
        if len(NUM.findall(ln)) >= 2 and len(ln) > 40:
            nums.append(ln)
    return heads, caps, text, nums

def main():
    for pid in IDS:
        abs_p = os.path.join(BASE, "abs_%s.html" % pid)
        htm_p = os.path.join(BASE, "html_%s.html" % pid)
        alt = os.path.join(BASE, "ar5iv_%s.html" % pid)
        src = htm_p
        if not (os.path.exists(htm_p) and os.path.getsize(htm_p) > 30000):
            if os.path.exists(alt) and os.path.getsize(alt) > 30000:
                src = alt
        abs_html = io.open(abs_p, "r", encoding="utf-8", errors="replace").read()
        m = meta(abs_html)
        L = []
        L.append("=" * 78)
        L.append("ID %s" % pid)
        L.append("SOURCE %s" % os.path.basename(src))
        L.append("TITLE %s" % m["title"])
        L.append("AUTHORS %s" % ("; ".join(m["authors"]) if m["authors"] else "NOT_FOUND"))
        L.append("AUTHOR_COUNT %d" % len(m["authors"]))
        L.append("DATE %s" % m["date"])
        L.append("DATELINE %s" % m["dateline"])
        L.append("COMMENTS %s" % m["comments"])
        L.append("SUBJECTS %s" % m["subjects"])
        L.append("ABSTRACT %s" % m["abstract"])
        L.append("")
        if not os.path.exists(src):
            L.append("HTML_MISSING -> body/headings/captions/numbers unavailable")
            body = "\n".join(L)
            io.open(os.path.join(BASE, "d_%s.txt" % pid), "w", encoding="utf-8", newline="\n").write(body + "\n")
            print("%-11s chars=%d heads=0 caps=0 nums=0 html=MISSING" % (pid, len(body)))
            continue
        raw = io.open(src, "r", encoding="utf-8", errors="replace").read()
        heads, caps, text, nums = skim(raw)
        L.append("--- HEADINGS (%d) ---" % len(heads))
        for lvl, h in heads:
            L.append("[%s] %s" % (lvl, h))
        L.append("")
        L.append("--- CAPTIONS (%d) ---" % len(caps))
        for c in caps:
            L.append("* " + c)
        L.append("")
        L.append("--- NUMERIC SENTENCES (%d) ---" % len(nums))
        for s in nums:
            L.append("- " + s)
        L.append("")
        L.append("--- BODY TEXT (first 12000 chars) ---")
        L.append(text[:12000])
        body = "\n".join(L)
        io.open(os.path.join(BASE, "d_%s.txt" % pid), "w", encoding="utf-8", newline="\n").write(body + "\n")
        print("%-11s chars=%d heads=%d caps=%d nums=%d src=%s" % (pid, len(body), len(heads), len(caps), len(nums), os.path.basename(src)))

main()
