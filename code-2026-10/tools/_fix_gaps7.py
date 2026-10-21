import io, re
txt = io.open("D:/hermes/analysis/_rd/pdf_2610.24453.txt", encoding="utf-8", errors="replace").read()
flat = re.sub(r"[ \t]+", " ", txt).replace("\n", " ")
pats = ["73.6", "64.3", "9.3", "86%", "82%", "83 ", "270", "665", "14.0", "16.0", "64.20", "81.50", "66.50", "83.80", "68.70", "85.63", "450"]
for p in pats:
    n = len(re.findall(re.escape(p), flat))
    print("PAT %-6s n=%d" % (p, n))
for p in ["73.6", "450 tasks", "83"]:
    for m in list(re.finditer(re.escape(p), flat))[:1]:
        print("[CTX %s] %s" % (p, flat[max(0, m.start()-110):m.start()+110]))
