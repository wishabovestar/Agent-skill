# -*- coding: utf-8 -*-
import glob, io, os, re, shutil, time

ARC = sorted([p for p in glob.glob("D:/hermes/analysis/PAPER_ARCHIVE_agent_memory_swarm_2026-10*.md")
              if ".bak" not in os.path.basename(p)])[-1]
CARDS = "D:/hermes/analysis/_cards/cards_529_536.md"
body = io.open(CARDS, encoding="utf-8").read().replace("\r\n", "\n")
ids = re.findall(r"(?m)^###\s(\d{3})\.", body)
stamp = time.strftime("%Y%m%d_%H%M%S")
bak = ARC + ".bak_%s_pre536" % stamp
shutil.copy2(ARC, bak)
before = io.open(ARC, encoding="utf-8").read()
b_lines = before.count("\n") + 1
b_ent = len(re.findall(r"(?m)^###\s\d{3}\.", before))
with io.open(ARC, "a", encoding="utf-8", newline="\n") as f:
    f.write("\n\n---\n\n" + body)
after = io.open(ARC, encoding="utf-8").read()
a_lines = after.count("\n") + 1
a_ent = len(re.findall(r"(?m)^###\s\d{3}\.", after))
new_ids = re.findall(r"(?m)^###\s(\d{3})\.", after)[-len(ids):]
print("CARDS ids=%s n=%d chars=%d" % (",".join(ids), len(ids), len(body)))
print("LINES %d -> %d (delta=%d)" % (b_lines, a_lines, a_lines - b_lines))
print("ENTRIES %d -> %d" % (b_ent, a_ent))
print("BYTES=%d" % os.path.getsize(ARC))
print("BAK=%s" % os.path.basename(bak))
print("NEW_IDS=%s" % ",".join(new_ids))
print("ALL8=%s" % (new_ids == ["%03d" % i for i in range(529, 537)]))
