# -*- coding: utf-8 -*-
import json, io, os, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
P = r"D:/hermes/hermes-data/profiles/mybot/skills"
ok = lambda b: "PASS" if b else "FAIL"

# frontmatter 回归检查（恢复技能 + 被我编辑过的技能）
for name, rel in (("attention-ab-validation", "mlops/attention-ab-validation"),
                  ("vps-remote-management", "devops/vps-remote-management"),
                  ("audit-team", "devops/audit-team")):
    md = os.path.join(P, rel, "SKILL.md")
    txt = open(md, encoding="utf-8", errors="replace").read()
    m = re.match(r"^---\s*\n(.*?)\n---", txt, re.S)
    fm_name = re.search(r"^name:\s*(.+)$", m.group(1), re.M).group(1).strip() if m else None
    print(f"  {name:26s} frontmatter={'ok' if m else 'BROKEN'} name={fm_name} {ok(bool(m) and fm_name == name)}")

# registry / 记忆 JSON 与结构完整性
u = json.load(open(os.path.join(P, ".usage.json"), encoding="utf-8"))
print("  .usage.json 解析 PASS, 条目:", len(u))
t = open(r"D:/hermes/hermes-data/profiles/mybot/memories/MEMORY.md", encoding="utf-8").read()
print(f"  MEMORY.md 解析 PASS, chars={len(t.rstrip(chr(10)))}/2200 = {100.0*len(t.rstrip(chr(10)))/2200:.1f}%")
print("  报告存在:",
      ok(os.path.isfile(r"D:/hermes/analysis/audit_reports/2026-09-21_mybot_internal-housekeeping-audit.md")))
print("  ledger 尾部:")
for line in open(os.path.join(P, ".curator_ledger.jsonl"), encoding="utf-8", errors="replace").read().splitlines()[-2:]:
    j = json.loads(line)
    print(f"    {j['ts'][:19]} {j['actor']} {j['action']} {j['skill']}")
