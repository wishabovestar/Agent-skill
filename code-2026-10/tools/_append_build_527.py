import glob, io, os, re, shutil, time

arc = None
for p in glob.glob("D:/hermes/analysis/PAPER_ARCHIVE_agent_memory_swarm_2026-10*.md"):
    if "bak" in os.path.basename(p):
        continue
    arc = p
assert arc, "archive not found"

src = "D:/hermes/analysis/_cards/cards_522_527.md"
data = io.open(src, encoding="utf-8").read()
if not data.endswith("\n"):
    data += "\n"

before = io.open(arc, encoding="utf-8").read()
b_lines = before.count("\n")
b_entries = len(re.findall(r"(?m)^###\s", before))

ts = time.strftime("%Y%m%d_%H%M%S")
bak = arc + ".bak_" + ts + "_pre527"
shutil.copy2(arc, bak)

head = "\n\n---\n\n"
io.open(arc, "ab").write((head + data).encode("utf-8"))

after = io.open(arc, encoding="utf-8").read()
a_lines = after.count("\n")
a_entries = len(re.findall(r"(?m)^###\s", after))
ids = re.findall(r"(?m)^###\s(\d{3})\.", after[-40000:])
ok = all(x in ids for x in ["522", "523", "524", "525", "526", "527"])

print("ARC=%s" % os.path.basename(arc))
print("LINES %d->%d  DELTA=%d  ENTRIES %d->%d" % (b_lines, a_lines, a_lines - b_lines, b_entries, a_entries))
print("NEW_IDS=%s ALL6=%s BAK=%s" % (",".join(ids[-8:]), ok, os.path.basename(bak)))
print("BYTES=%d" % os.path.getsize(arc))
