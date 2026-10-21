# -*- coding: utf-8 -*-
"""内部整理审计 v2.0 (维度10-12) — 2026-09-21
输出 JSON 报告到 D:/hermes/analysis/_hk_audit_20260921.json
"""
import json, os, re, sys, io, datetime, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HOME = r"C:/Users/Administrator"
PROF = r"D:/hermes/hermes-data/profiles/mybot"
SKILLS = os.path.join(PROF, "skills")
AGENTS_SKILLS = os.path.join(HOME, ".agents/skills")
MEM = os.path.join(PROF, "memories")
NOW = datetime.datetime.now(datetime.timezone.utc)
NOW_TS = time.time()

R = {}

def readf(p, n=100000):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read(n)
    except Exception as e:
        return ""

# ---------- A. 记忆空间 ----------
mem_txt = readf(os.path.join(MEM, "MEMORY.md"))
usr_txt = readf(os.path.join(MEM, "USER.md"))
R["memory"] = {
    "memory_chars": len(mem_txt.rstrip("\n")),
    "memory_limit": 2200,
    "user_chars": len(usr_txt.rstrip("\n")),
    "user_limit": 1375,
}
R["memory"]["memory_pct"] = round(100.0 * R["memory"]["memory_chars"] / 2200, 1)
R["memory"]["user_pct"] = round(100.0 * R["memory"]["user_chars"] / 1375, 1)

blocks = [b.strip() for b in mem_txt.split("§") if b.strip()]
R["memory"]["blocks"] = len(blocks)
# 块级重复检测（前40字符相同 / 全文相同）
dups = []
for i in range(len(blocks)):
    for j in range(i + 1, len(blocks)):
        a, b = blocks[i], blocks[j]
        if a == b:
            dups.append({"type": "exact", "a": a[:60], "b": b[:60]})
        else:
            # 词集 jaccard
            sa = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", a))
            sb = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", b))
            if sa and sb:
                jac = len(sa & sb) / len(sa | sb)
                if jac >= 0.40:
                    dups.append({"type": "near", "jac": round(jac, 2), "a": a[:70], "b": b[:70],
                                 "shared": sorted(sa & sb)[:12]})
R["memory"]["dup_blocks"] = dups

# 跨区重复 (MEMORY vs USER)
sa = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", mem_txt))
sb = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", usr_txt))
R["memory"]["cross_jaccard"] = round(len(sa & sb) / len(sa | sb), 3)
R["memory"]["cross_shared"] = sorted(sa & sb)

# 记忆中引用的技能名 -> 是否仍活跃
skill_refs = set(re.findall(r"skill=([a-z0-9\-]+)", mem_txt))
skill_refs |= set(re.findall(r"([a-z0-9\-]+)\s*技能", mem_txt))
R["memory"]["skill_refs"] = sorted(skill_refs)

# ---------- B. 技能库 ----------
def is_skill_dir(d):
    return os.path.isfile(os.path.join(d, "SKILL.md"))

active_names = {}
skipped = []
for base, tag in ((SKILLS, "mybot"), (AGENTS_SKILLS, "agents")):
    if not os.path.isdir(base):
        continue
    for root, dirs, files in os.walk(base):
        rel = os.path.relpath(root, base)
        parts = [p for p in rel.split(os.sep) if p not in (".", "")]
        if any(p.startswith(".") for p in parts):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if "SKILL.md" not in files:
            continue
        name = os.path.basename(root)
        txt = readf(os.path.join(root, "SKILL.md"), 3000)
        m = re.match(r"^---\s*\n(.*?)\n---", txt, re.S)
        fmname, desc, tags = name, "", ""
        if m:
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip().lower()
                    if k == "name":
                        fmname = v.strip().strip('"').strip("'")
                    elif k == "description":
                        desc = v.strip().strip('"').strip("'")
                    elif k == "tags":
                        tags = v.strip()
        active_names.setdefault(fmname, []).append({"dir": root, "tag": tag,
                                                     "desc": desc[:200], "tags": tags})

archived = []
arch_dir = os.path.join(SKILLS, ".archive")
if os.path.isdir(arch_dir):
    archived = sorted(os.listdir(arch_dir))

R["skills"] = {
    "active_unique_names": len(active_names),
    "active_files": sum(len(v) for v in active_names.values()),
    "dup_names": {k: [x["dir"] for x in v] for k, v in active_names.items() if len(v) > 1},
    "archived_count": len(archived),
    "archived": archived,
}

# 使用统计
usage_p = os.path.join(SKILLS, ".usage.json")
usage = json.loads(readf(usage_p)) if os.path.isfile(usage_p) else {}
dead, never, stale60 = [], [], []
for k, v in usage.items():
    uc = v.get("use_count", 0) or 0
    lw = v.get("last_used_at") or v.get("last_viewed_at") or v.get("created_at")
    if v.get("archived_at"):
        continue
    if uc == 0:
        never.append({"name": k, "state": v.get("state"), "created": (v.get("created_at") or "")[:10]})
        continue
    if lw:
        try:
            d = datetime.datetime.fromisoformat(lw.replace("Z", "+00:00"))
            age = (NOW - d).days
        except Exception:
            age = -1
        if age > 90:
            dead.append({"name": k, "age_days": age, "use_count": uc, "last": lw[:10]})
        elif age > 60:
            stale60.append({"name": k, "age_days": age, "use_count": uc, "last": lw[:10]})
R["skills"]["usage_entries"] = len(usage)
R["skills"]["never_used"] = sorted(never, key=lambda x: x["name"])
R["skills"]["dead_gt90d"] = sorted(dead, key=lambda x: -x["age_days"])
R["skills"]["stale_60_90d"] = sorted(stale60, key=lambda x: -x["age_days"])

# 归档技能被活跃引用检测（记忆 + 技能互引 + cron）
refs_to_archived = []
arch_set = set(archived)
all_text = {}
for base in (SKILLS, AGENTS_SKILLS):
    for root, dirs, files in os.walk(base):
        parts = [p for p in os.path.relpath(root, base).split(os.sep) if p not in (".", "")]
        if any(p.startswith(".") for p in parts):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.endswith(".md"):
                all_text[os.path.join(root, f)] = readf(os.path.join(root, f), 20000)

for path, txt in all_text.items():
    for a in arch_set:
        if len(a) < 5:
            continue
        for m in re.finditer(re.escape(a), txt):
            snipped = txt[max(0, m.start() - 40):m.start() + 60].replace("\n", " ")
            refs_to_archived.append({"skill": a, "ref_in": path, "ctx": snipped.strip()[:110]})
            break

R["skills"]["refs_to_archived"] = refs_to_archived

# ---------- C. Cron / 工作流 ----------
jobs_p = os.path.join(PROF, "cron", "jobs.json")
jobs_raw = json.loads(readf(jobs_p)) if os.path.isfile(jobs_p) else {}
jl = jobs_raw.get("jobs", jobs_raw) if isinstance(jobs_raw, dict) else jobs_raw
if isinstance(jl, dict):
    jl = list(jl.values())

cron_rows = []
for j in jl:
    cron_rows.append({
        "id": (j.get("id") or "")[:12],
        "name": j.get("name"),
        "schedule": j.get("schedule"),
        "enabled": j.get("enabled"),
        "paused": j.get("paused"),
        "no_agent": j.get("no_agent"),
        "script": j.get("script"),
        "model": (j.get("model") or {}).get("model") if isinstance(j.get("model"), dict) else j.get("model"),
        "last_status": j.get("last_status"),
        "last_run_at": (j.get("last_run_at") or "")[:19],
        "failure_streak": j.get("failure_streak"),
        "last_delivery_error": (j.get("last_delivery_error") or "")[:90],
        "delivery_platform": ((j.get("origin") or {}).get("platform") if isinstance(j.get("origin"), dict) else None),
    })
R["cron"] = {
    "total": len(cron_rows),
    "enabled": sum(1 for c in cron_rows if c["enabled"]),
    "no_model": [c for c in cron_rows if not c["model"]],
    "error_status": [c for c in cron_rows if c["last_status"] == "error"],
    "delivery_failed": [c for c in cron_rows if c["last_delivery_error"]],
    "blocked": [c for c in cron_rows if c["last_status"] == "blocked_config"],
    "never_run": [c for c in cron_rows if not c["last_run_at"]],
    "no_agent_jobs": [c for c in cron_rows if c["no_agent"]],
}
# 脚本存在性
missing_scripts = []
for c in cron_rows:
    s = c.get("script")
    if s:
        cands = [os.path.join(PROF, "scripts", s), os.path.join(PROF, s), s]
        if not any(os.path.isfile(x) for x in cands):
            missing_scripts.append({"job": c["name"], "script": s})
R["cron"]["missing_scripts"] = missing_scripts

# cron prompt 中引用的技能是否存在
prompt_skill_refs = []
for j in jl:
    p = (j.get("prompt") or "")
    for m in re.finditer(r"([a-z][a-z0-9]+(?:-[a-z0-9]+){1,4})", p):
        tok = m.group(1)
        if tok in arch_set:
            prompt_skill_refs.append({"job": j.get("name"), "ref": tok})
R["cron"]["prompt_refs_archived_skills"] = sorted({(x["job"], x["ref"]) for x in prompt_skill_refs})

# ---------- D. 工作流/文档一致性 ----------
# audit-team / 技能文档中引用的 references 断链
broken_refs = []
for path, txt in all_text.items():
    for m in re.finditer(r"references[/\\]([\w\-\.]+\.md)", txt):
        tgt = m.group(1)
        skill_root = path
        # 找 SKILL.md 所在目录
        d = os.path.dirname(path)
        while d and not os.path.isfile(os.path.join(d, "SKILL.md")):
            nd = os.path.dirname(d)
            if nd == d:
                break
            d = nd
        if not d or not os.path.isfile(os.path.join(d, "SKILL.md")):
            continue
        if not os.path.isfile(os.path.join(d, "references", tgt)):
            broken_refs.append({"file": path, "missing": tgt})
grp = {}
for b in broken_refs:
    grp.setdefault(b["file"], []).append(b["missing"])
R["workflow"] = {
    "broken_reference_total": len(broken_refs),
    "broken_by_file": {k: sorted(set(v)) for k, v in sorted(grp.items(), key=lambda x: -len(x[1]))[:15]},
    "md_files_scanned": len(all_text),
}

out = json.dumps(R, ensure_ascii=False, indent=1)
open(r"D:/hermes/analysis/_hk_audit_20260921.json", "w", encoding="utf-8").write(out)

# ---- 摘要打印 ----
print("== 记忆 ==", R["memory"]["memory_chars"], "/2200 =", R["memory"]["memory_pct"], "% ; USER",
      R["memory"]["user_chars"], "/1375 =", R["memory"]["user_pct"], "%")
print("blocks:", R["memory"]["blocks"], "dup_blocks:", len(dups), "cross_jac:", R["memory"]["cross_jaccard"])
for d in dups:
    print("  DUP", d["type"], d.get("jac", ""), "|", d["a"], "<->", d["b"])
print("mem skill_refs:", R["memory"]["skill_refs"])
print("\n== 技能 ==", R["skills"]["active_unique_names"], "unique /", R["skills"]["active_files"], "files; archived:",
      R["skills"]["archived_count"])
print("dup_names:", {k: len(v) for k, v in R["skills"]["dup_names"].items()})
for k, v in list(R["skills"]["dup_names"].items())[:60]:
    print("   DUP", k, "->", [x.replace("D:/hermes/hermes-data/profiles/mybot/skills", "P").replace("C:/Users/Administrator/.agents/skills", "A") for x in v])
print("usage entries:", R["skills"]["usage_entries"], "never:", len(R["skills"]["never_used"]),
      "dead>90d:", len(R["skills"]["dead_gt90d"]), "stale60-90:", len(R["skills"]["stale_60_90d"]))
for d in R["skills"]["dead_gt90d"][:10]:
    print("  DEAD", d)
print("refs_to_archived:", len(R["skills"]["refs_to_archived"]))
for r in R["skills"]["refs_to_archived"][:15]:
    print("   ", r["skill"], "<-", r["ref_in"].replace(SKILLS, "SKILLS"), "|", r["ctx"][:70])
print("\n== Cron ==", R["cron"]["total"], "jobs; enabled", R["cron"]["enabled"])
print("no_model:", len(R["cron"]["no_model"]), "error:", len(R["cron"]["error_status"]),
      "delivery_failed:", len(R["cron"]["delivery_failed"]), "blocked:", len(R["cron"]["blocked"]),
      "never_run:", len(R["cron"]["never_run"]), "missing_scripts:", len(R["cron"]["missing_scripts"]))
for c in R["cron"]["error_status"][:10]:
    print("  ERR", c["id"], c["name"], c["failure_streak"], c["last_run_at"])
for c in R["cron"]["delivery_failed"][:10]:
    print("  DELIV", c["id"], c["name"], c["delivery_platform"], "|", c["last_delivery_error"])
for c in R["cron"]["blocked"][:10]:
    print("  BLOCKED", c["id"], c["name"], c["failure_streak"])
print("prompt_refs_archived:", R["cron"]["prompt_refs_archived_skills"])
print("\n== 工作流 ==", "broken refs:", R["workflow"]["broken_reference_total"], "in",
      R["workflow"]["md_files_scanned"], "files")
for f, ms in list(R["workflow"]["broken_by_file"].items())[:6]:
    print("  ", f.replace(SKILLS, "SKILLS"), len(ms), ms[:4])
print("\nJSON -> D:/hermes/analysis/_hk_audit_20260921.json")
