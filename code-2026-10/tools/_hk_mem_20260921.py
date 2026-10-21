# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"D:/hermes/hermes-data/profiles/mybot/memories/MEMORY.md"
t = open(p, encoding="utf-8").read()
n = len(t.rstrip("\n"))
print(f"MEMORY chars={n} / 2200 = {100.0*n/2200:.1f}%")
u = open(r"D:/hermes/hermes-data/profiles/mybot/memories/USER.md", encoding="utf-8").read()
print(f"USER   chars={len(u.rstrip(chr(10)))} / 1375 = {100.0*len(u.rstrip(chr(10)))/1375:.1f}%")
for i, line in enumerate(t.splitlines(), 1):
    if line.strip():
        print(f"  {len(line):4d}  {line[:60]}")
