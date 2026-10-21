# -*- coding: utf-8 -*-
"""P0-2/P0-3: 重新激活并置顶被 MEMORY 引用的两个技能；写入 curator ledger 供追溯。"""
import json, io, os, sys, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
P = r"D:/hermes/hermes-data/profiles/mybot/skills"
UP = os.path.join(P, ".usage.json")
now = datetime.datetime.now(datetime.timezone.utc).isoformat()

u = json.load(open(UP, encoding="utf-8"))
changed = []
for name, newpath in (("attention-ab-validation", "mlops/attention-ab-validation"),
                      ("vps-remote-management", "devops/vps-remote-management")):
    e = u.get(name)
    if not e:
        print(f"  !! {name} 无 usage 条目 — 跳过")
        continue
    before = {k: e.get(k) for k in ("state", "archived_at", "pinned")}
    e["state"] = "active"
    e["archived_at"] = None
    e["pinned"] = True
    changed.append((name, before, {"state": e["state"], "archived_at": e["archived_at"], "pinned": e["pinned"]}))

json.dump(u, open(UP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.load(open(UP, encoding="utf-8"))  # 验证可解析
print("usage.json 更新:")
for c in changed:
    print("  ", c[0], c[1], "->", c[2])

led = os.path.join(P, ".curator_ledger.jsonl")
with open(led, "a", encoding="utf-8") as f:
    for i, (name, before, after) in enumerate(changed):
        rec = {
            "id": f"hk20260921-{i}",
            "ts": now,
            "actor": "audit-team",
            "action": "restore",
            "skill": name,
            "evidence": {
                "reason": "9/18 curator 自动归档后 MEMORY 指针悬空; 内容经比对为完整版本",
                "before": before, "after": after,
                "source": "内部整理审计 2026-09-21 (audit-team 维度10-12)",
            },
        }
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
print("ledger 追加:", [c[0] for c in changed])
