#!/usr/bin/env python3
"""
技能自演化引擎 — JiuwenSwarm Skill Self-Evolution 落地
=======================================================
JiuwenSwarm 核心: 检测错误信号/用户不满 → 自动优化 Skill 定义

本引擎为 Hermes 技能体系落地此机制的前置: "技能健康状态追踪"
  1. 扫描所有技能 SKILL.md (frontmatter: name/description)
  2. 从 session DB 检测技能相关错误信号 (error/exception/失败)
  3. 维护 技能健康库 (health_db.json): 状态✅/⚠️/❌ + 错误信号 + 优化建议
  4. 输出"待优化技能"清单 (供后续针对性更新SKILL.md)

用法:
  python skill_self_evolution.py           # 全量扫描+检测
  python skill_self_evolution.py --status  # 查看健康库
  python skill_self_evolution.py --list    # 列出所有技能
"""
import json, os, sys, sqlite3, re
from datetime import datetime
from pathlib import Path

# 路径
KB = Path(r"D:\hermes\hermes-data\profiles\qqbot3")
SKILLS_DIR = KB / "skills"
HEALTH_DB = KB / "knowledge_base" / "audit" / "skill_health_db.json"
STATE_DB = KB / "state.db"

# 错误信号关键词 (技能使用失败的指标)
ERROR_SIGNALS = [
    "skill failed", "skill error", "skillexception", "failed to load skill",
    "skill not found", "unknown skill", "skill error:", "skill 不存在",
    "error loading skill", "skill 失败", "rollback skill", "skill crash",
]

def scan_skills():
    """扫描所有技能的 SKILL.md, 提取 name/description/brief"""
    skills = []
    if not SKILLS_DIR.exists():
        print(f"❌ skills 目录不存在: {SKILLS_DIR}")
        return skills
    for skmd in SKILLS_DIR.rglob("SKILL.md"):
        try:
            text = skmd.read_text(encoding="utf-8", errors="replace")
            name = ""
            desc = ""
            # 解析 frontmatter
            m = re.search(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
            if m:
                fm = m.group(1)
                nm = re.search(r"^\s*name:\s*(.+)$", fm, re.M)
                dm = re.search(r"^\s*description:\s*(?:\"|')?(.+?)(?:\"|')?\s*$", fm, re.M)
                if nm: name = nm.group(1).strip()
                if dm: desc = dm.group(1).strip()[:120]
            if not name:
                name = skmd.parent.name
            # 相对路径
            rel = str(skmd.relative_to(SKILLS_DIR))
            skills.append({"name": name, "description": desc,
                           "path": rel, "dir": skmd.parent.name,
                           "brief": desc[:100]})
        except Exception:
            continue
    return skills

def detect_errors_from_db():
    """从 session DB 检测技能相关错误信号"""
    sig_counts = {}
    samples = []
    if not STATE_DB.exists():
        return sig_counts, samples
    try:
        conn = sqlite3.connect(str(STATE_DB))
        rows = conn.execute(
            "SELECT content FROM messages WHERE content IS NOT NULL "
            "AND (content LIKE '%skill%' OR content LIKE '%Skill%') "
            "AND lower(content) LIKE '%error%' ORDER BY id DESC LIMIT 200"
        ).fetchall()
        conn.close()
        for (content,) in rows:
            low = content.lower()
            for sig in ERROR_SIGNALS:
                if sig in low:
                    sig_counts[sig] = sig_counts.get(sig, 0) + 1
                    if len(samples) < 5:
                        samples.append(content[:150])
    except Exception as e:
        print(f"⚠️ DB 检测失败: {e}")
    return sig_counts, samples

def load_health_db():
    if HEALTH_DB.exists():
        return json.loads(HEALTH_DB.read_text(encoding="utf-8"))
    return {"version": 1, "skills": {}}

def save_health_db(db):
    HEALTH_DB.parent.mkdir(exist_ok=True)
    # 原子写 (align nanobot design)
    tmp = HEALTH_DB.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, HEALTH_DB)

def run():
    print("="*60)
    print("技能自演化引擎 (JiuwenSwarm Skill Self-Evolution)")
    print("="*60)
    skills = scan_skills()
    print(f"\n扫描到 {len(skills)} 个技能 (SKILL.md)")
    sigs, samples = detect_errors_from_db()
    print(f"检测到技能相关错误信号: {len(sigs)} 种")
    for sig, cnt in sorted(sigs.items()):
        print(f"  ⚠️ {sig}: {cnt}次")

    # 更新健康库
    db = load_health_db()
    now = datetime.now().isoformat()
    new_skills = 0
    for s in skills:
        key = s["name"]
        entry = db["skills"].get(key, {"first_seen": now, "errors": 0, "status": "✅"})
        entry["path"] = s["path"]
        entry["brief"] = s["brief"]
        entry["last_scan"] = now
        # 若有通用错误信号, 标记⚠️待观察 (命中错误总数>0)
        if sigs and s["name"].lower() in [x.lower() for x in sigs.keys()]:
            entry["status"] = "⚠️"
        db["skills"].setdefault(key, entry)
        if "first_seen" in db["skills"] and db["skills"][key]["first_seen"] == now:
            new_skills += 1
    save_health_db(db)

    # 汇总
    total = len(db["skills"])
    ok = sum(1 for s in db["skills"].values() if s["status"] == "✅")
    warn = sum(1 for s in db["skills"].values() if s["status"] == "⚠️")
    print(f"\n健康库: {total} 技能 | ✅{ok} | ⚠️{warn} | 新增{new_skills}")
    print(f"存档: {HEALTH_DB}")

    # 待优化建议
    print("\n【待优化技能】(错误信号>0 或 ⚠️):")
    atrisk = [k for k, s in db["skills"].items() if s["status"] == "⚠️"]
    if atrisk:
        for k in atrisk[:10]:
            print(f"  🔧 {k}")
    else:
        print("  (暂无, 技能健康)")

if __name__ == "__main__":
    if "--status" in sys.argv:
        db = load_health_db()
        print("=== 技能健康库 ===")
        for k, s in db["skills"].items():
            print(f"  {s['status']} {k}: {s.get('brief','')[:40]}")
    elif "--list" in sys.argv:
        skills = scan_skills()
        for s in skills[:20]:
            print(f"  {s['name']}: {s['brief']}")
    else:
        run()
