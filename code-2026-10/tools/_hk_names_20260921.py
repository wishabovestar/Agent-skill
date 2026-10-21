# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
snap = json.load(open(r"D:/hermes/hermes-data/profiles/mybot/.skills_prompt_snapshot.json", encoding="utf-8"))
names = sorted(e.get("frontmatter_name") or e.get("skill_name") for e in snap["skills"])
print(len(names))
for i in range(0, len(names), 6):
    print("  " + " | ".join((n or "?")[:26].ljust(26) for n in names[i:i+6]))
