import io
lines = io.open("D:/hermes/analysis/_rd/pdf_2610.24453.txt", encoding="utf-8", errors="replace").read().splitlines()
for i in range(320, 372):
    s = lines[i].rstrip()
    if s.strip():
        print("%d|%s" % (i + 1, s[:150]))
