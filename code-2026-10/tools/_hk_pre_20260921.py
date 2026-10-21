# -*- coding: utf-8 -*-
import json, os, io, sys, shutil, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
P = r"D:/hermes/hermes-data/profiles/mybot/skills"
snap = json.load(open(r"D:/hermes/hermes-data/profiles/mybot/.skills_prompt_snapshot.json", encoding="utf-8"))
names = {e.get("frontmatter_name") or e.get("skill_name") for e in snap["skills"]}
for n in ("vps-remote-management", "vps-remote-ops", "attention-ab-validation", "data-privacy",
          "codebase-research", "arxiv.bak"):
    print(f"  snapshot contains {n:28s} -> {n in names}")
print("snapshot entries:", len(snap["skills"]))
