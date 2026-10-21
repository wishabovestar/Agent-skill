import io, re
txt = io.open("D:/hermes/analysis/_rd/pdf_2610.24453.txt", encoding="utf-8", errors="replace").read()
flat = re.sub(r"[ \t]+", " ", txt)
for pat in ["412", "193", "46.8", "192", "fortuitous", "$1.93", "2.17", "12.4", "69.27", "74.75"]:
    hits = [m.start() for m in re.finditer(re.escape(pat), flat)]
    print("PAT %-12s n=%d" % (pat, len(hits)))
    for h in hits[:2]:
        seg = flat[max(0, h - 90):h + 90].replace("\n", " ")
        print("   ...%s..." % seg)
