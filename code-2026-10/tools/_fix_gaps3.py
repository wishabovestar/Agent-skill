import io
lines = io.open("D:/hermes/analysis/_rd/pdf_2610.24453.txt", encoding="utf-8", errors="replace").read().splitlines()
idx = [i for i, L in enumerate(lines) if L.strip().startswith("Hippo ")]
print("hippo_rows=%d at %s" % (len(idx), idx))
for i in idx:
    blk = [lines[j].rstrip() for j in range(max(0, i - 7), i + 1)]
    print("=== row %d ===" % (i + 1))
    for b in blk:
        if b.strip():
            print("   |%s" % b[:120])
