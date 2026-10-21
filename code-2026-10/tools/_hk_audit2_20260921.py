# -*- coding: utf-8 -*-
import json, os, re, io, sys, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
P = r"D:/hermes/hermes-data/profiles/mybot/skills"
A = r"C:/Users/Administrator/.agents/skills"
R = json.load(open(r"D:/hermes/analysis/_hk_audit_20260921.json", encoding="utf-8"))

# 1) 归档技能被引用聚合
agg = {}
for r in R["skills"]["refs_to_archived"]:
    agg.setdefault(r["skill"], []).append(r["ref_in"].replace(P, "P").replace(A, "A"))
print("== 归档技能被活跃文档引用 (Top) ==")
for k, v in sorted(agg.items(), key=lambda x: -len(x[1]))[:25]:
    print(f"  {k:38s} {len(v):3d}  {v[0][:70]}")

# 2) .bak / 重复目录在活跃树中
print("\n== 活跃树中的 .bak / dup 目录 ==")
for base in (P, A):
    for root, dirs, files in os.walk(base):
        rel = os.path.relpath(root, base)
        if any(x.startswith(".") for x in rel.split(os.sep) if x not in (".", "")):
            dirs[:] = []
            continue
        for d in list(dirs):
            if ".bak" in d or d.endswith("-dup") or "copy" in d.lower():
                full = os.path.join(root, d)
                has = os.path.isfile(os.path.join(full, "SKILL.md"))
                print(f"  {'SKILL' if has else 'empty'} {full.replace(base,'P' if base==P else 'A')}")

# 3) 提示词快照成本
snap = os.path.join(r"D:/hermes/hermes-data/profiles/mybot", ".skills_prompt_snapshot.json")
j = json.load(open(snap, encoding="utf-8"))
def count(obj):
    if isinstance(obj, list):
        return len(obj), sum(len(json.dumps(x, ensure_ascii=False)) for x in obj)
    if isinstance(obj, dict):
        tot = 0
        for k, v in obj.items():
            if isinstance(v, dict) and ("description" in v or "name" in v):
                tot += len(str(v.get("name", ""))) + len(str(v.get("description", "")))
            elif isinstance(v, str):
                tot += len(v)
        return len(obj), tot
    return -1, -1
n, ch = count(j)
print(f"\n== 提示词快照 == type={type(j).__name__} entries={n} name+desc chars≈{ch} (~{ch//4} tokens)")

# 4) cron no_agent vs model
jl = json.load(open(r"D:/hermes/hermes-data/profiles/mybot/cron/jobs.json", encoding="utf-8"))
jl = jl.get("jobs", jl) if isinstance(jl, dict) else jl
if isinstance(jl, dict):
    jl = list(jl.values())
print("\n== cron: 缺 model 且需要 LLM 的 job ==")
for j in jl:
    m = j.get("model")
    has_model = bool(m if not isinstance(m, dict) else m.get("model"))
    if not has_model and not j.get("no_agent"):
        print(f"  {str(j.get('id'))[:12]} {j.get('name')} agent={not j.get('no_agent')} status={j.get('last_status')} last={(j.get('last_run_at') or '')[:19]}")
print("\n== cron no_agent 脚本 job (model 无关) ==")
for j in jl:
    if j.get("no_agent"):
        print(f"  {str(j.get('id'))[:12]} {j.get('name')} script={j.get('script')} status={j.get('last_status')} last={(j.get('last_run_at') or '')[:19]}")

# 5) 记忆引用的技能是否还在活跃树
print("\n== 记忆引用技能存活检查 ==")
for name in R["memory"]["skill_refs"] + ["lsa-hi-sparse-attention", "vps-remote-management", "attention-ab-validation"]:
    hits = []
    for base, tag in ((P, "P"), (A, "A")):
        for root, dirs, files in os.walk(base):
            rel = os.path.relpath(root, base)
            parts = [x for x in rel.split(os.sep) if x not in (".", "")]
            if any(x.startswith(".") for x in parts):
                dirs[:] = []
                continue
            if os.path.basename(root) == name and "SKILL.md" in files:
                hits.append(tag + "/" + rel)
    print(f"  {name:32s} active={hits if hits else 'NONE (已归档/不存在)'}")
