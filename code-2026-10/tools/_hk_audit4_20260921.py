# -*- coding: utf-8 -*-
import json, os, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
P = r"D:/hermes/hermes-data/profiles/mybot/skills"

print("== .usage.json 条目 ==")
u = json.load(open(os.path.join(P, ".usage.json"), encoding="utf-8"))
for n in ("vps-remote-management", "vps-remote-ops", "attention-ab-validation",
          "data-privacy", "codebase-research", "lsa-hi-sparse-attention"):
    e = u.get(n)
    print(f"  {n:28s} {json.dumps(e, ensure_ascii=False) if e else 'NO ENTRY'}")

print("\n== curator ledger 中的归档记录 (原始路径) ==")
led = os.path.join(P, ".curator_ledger.jsonl")
if os.path.isfile(led):
    targets = {"vps-remote-management", "vps-remote-ops", "attention-ab-validation", "data-privacy"}
    with open(led, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                j = json.loads(line)
            except Exception:
                continue
            s = json.dumps(j, ensure_ascii=False)
            for t in targets:
                if t in s:
                    print("  ", s[:400])
                    targets.discard(t)
                    break
    print("  未找到:", targets)

print("\n== .archive 顶层中的目标目录 ==")
for n in ("vps-remote-management", "vps-remote-ops", "attention-ab-validation", "data-privacy"):
    d = os.path.join(P, ".archive", n)
    print(f"  {n}: {sorted(os.listdir(d)) if os.path.isdir(d) else 'MISSING'}")

print("\n== 归档技能的 frontmatter name 与 mtime ==")
import time
for n in ("vps-remote-management", "vps-remote-ops", "attention-ab-validation", "data-privacy"):
    md = os.path.join(P, ".archive", n, "SKILL.md")
    if os.path.isfile(md):
        t = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(md)))
        txt = open(md, encoding="utf-8", errors="replace").read(400)
        name = ""
        for l in txt.splitlines():
            if l.startswith("name:"):
                name = l.split(":", 1)[1].strip()
        print(f"  {n:28s} name={name:28s} mtime={t}")
