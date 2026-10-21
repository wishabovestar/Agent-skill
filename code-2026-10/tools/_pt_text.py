# -*- coding: utf-8 -*-
import io, os, re, subprocess, glob

PT = "D:/hermes/analysis/_pt/"

def detag(h):
    h = re.sub(r"(?is)<(script|style|math|sup)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?i)</(p|div|h[1-6]|li|tr|section|figcaption)>", "\n", h)
    h = re.sub(r"(?i)<br\s*/?>", "\n", h)
    h = re.sub(r"<[^>]+>", " ", h)
    h = h.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    h = re.sub(r"[ \t]+", " ", h)
    h = re.sub(r"\n{2,}", "\n", h)
    return h

for tag in ["100366", "100383", "100397"]:
    fp = PT + "t_%s.html" % tag
    if os.path.exists(fp):
        txt = detag(io.open(fp, encoding="utf-8", errors="replace").read())
        io.open(PT + "x_%s.txt" % tag, "w", encoding="utf-8", newline="\n").write(txt)
        print("HTML %s chars=%d lines=%d" % (tag, len(txt), txt.count("\n") + 1))

pdf = PT + "p_100371.pdf"
if os.path.exists(pdf) and os.path.getsize(pdf) > 10000:
    r = subprocess.run([r"C:/Program Files/Git/mingw64/bin/pdftotext.exe", "-layout", pdf, PT + "x_100371.txt"],
                       capture_output=True, text=True)
    if not os.path.exists(PT + "x_100371.txt"):
        r = subprocess.run(["pdftotext", "-layout", pdf, PT + "x_100371.txt"], capture_output=True, text=True)
    t = io.open(PT + "x_100371.txt", encoding="utf-8", errors="replace").read() if os.path.exists(PT + "x_100371.txt") else ""
    print("PDF 100371 rc=%s chars=%d lines=%d perr=%s" % (r.returncode, len(t), t.count("\n") + 1, (r.stderr or "")[:60]))
print("DONE")
