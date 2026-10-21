# -*- coding: utf-8 -*-
import os, json, io, sys, difflib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
P = r"D:/hermes/hermes-data/profiles/mybot/skills"
A = r"C:/Users/Administrator/.agents/skills"

print("== 1. 缺失的 references 目标文件 ==")
for target in ("security-audit-methodology.md", "sandbox-test-methodology.md",
               "2026-07-13-weixin-session-timeout.md", "2026-07-09-sandbox-simulation-report.md",
               "2026-07-28-multi-profile-cleanup.md", "2026-08-28-lock-arbitration.md"):
    found = []
    for base in (P, A):
        for root, dirs, files in os.walk(base):
            if target in files:
                found.append(os.path.join(root, target).replace(base, "P" if base == P else "A"))
    print(f"  {target:42s} -> {found if found else 'NOT FOUND'}")

print("\n== 2. .archive 中的相关技能 ==")
for n in ("vps-remote-management", "vps-remote-ops", "attention-ab-validation", "attention-compression",
          "attention-kv-compression", "gateway-watchdog"):
    d = os.path.join(P, ".archive", n)
    if os.path.isdir(d):
        md = os.path.join(d, "SKILL.md")
        print(f"  {n}: exists, SKILL.md={'yes' if os.path.isfile(md) else 'no'}, files={len(os.listdir(d))}")

print("\n== 3. .bak vs canonical 差异摘要 ==")
for n in ("arxiv", "competitor-news-monitor", "grounded-citations"):
    a = open(os.path.join(A, "research", n, "SKILL.md"), encoding="utf-8", errors="replace").read()
    b = open(os.path.join(A, "research", n + ".bak", "SKILL.md"), encoding="utf-8", errors="replace").read()
    dl = [l for l in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0)][2:]
    print(f"  {n}: canonical={len(a)}c bak={len(b)}c diff_lines={len(dl)}")
    for l in dl[:6]:
        print("      ", l[:120])

print("\n== 4. 提示词快照结构 ==")
d = json.load(open(os.path.join(P, "..", ".skills_prompt_snapshot.json"), encoding="utf-8"))
for k, v in d.items():
    print(f"  {k}: {type(v).__name__} len={len(v) if hasattr(v,'__len__') else ''}")
inner = None
for k, v in d.items():
    if isinstance(v, list) and v and isinstance(v[0], dict):
        inner = v
        key = k
if inner:
    print(f"  -> list '{key}': {len(inner)} entries; sample keys={list(inner[0].keys())}")
    tot = sum(len(str(e.get("name", ""))) + len(str(e.get("description", ""))) for e in inner)
    print(f"  name+description total chars = {tot} (~{tot//4} tokens)")
    names = [e.get("name") for e in inner]
    dup = {n: names.count(n) for n in set(names) if names.count(n) > 1}
    print(f"  重名条目 ({len(dup)}): {sorted(dup.items(), key=lambda x:-x[1])[:15]}")
    bak = [n for n in names if n and ".bak" in n]
    print(f"  含 .bak 条目: {bak}")
