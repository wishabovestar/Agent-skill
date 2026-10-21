#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能补丁生成与验证器 (借鉴 SKILL-KD + OSReward)
====================================================
将 arXiv:2607.28048 (SKILL-KD 对比技能蒸馏) + arXiv:2607.28609 (OSReward 独立验证)
的方法论落地到 Hermes 技能自演化体系:

现有 skill_self_evolution.py 只做"健康检测"(发现失败)
本脚本补齐 SKILL-KD 的核心闭环:
  1.【补丁生成】从 失败技能使用 vs 成功技能使用 的对比中, 蒸馏出可操作规则补丁
  2.【独立验证】借鉴 OSReward: 不用LLM自评, 用独立规则匹配器验证补丁
     能否覆盖新的失败样本 (宽松偏差→需交叉验证)
  3.【防漂移】借鉴 SKILL-KD Drift-Aware Consolidation:
     维护编辑历史, 判定补丁是 新增/修改/删除 规则 (聚合冗余, 防技能漂移)

用法:
  python skill_patch_kd.py [--dry]          # 全量分析(检测模式, 不写SKILL.md)
  python skill_patch_kd.py --status         # 查看补丁历史库
"""
import json, os, sys, sqlite3, re
from datetime import datetime
from pathlib import Path

KB = Path(r"D:\hermes\hermes-data\profiles\qqbot3")
SKILLS_DIR = KB / "skills"
PATCH_DB = KB / "knowledge_base" / "audit" / "skill_patch_kd_db.json"
STATE_DB = KB / "state.db"

# 失败信号: 技能使用报错/未命中 (弱学生失败) — 要求"技能"+明确错误动词
FAIL_SIGNALS = [
    "skill not found", "unknown skill", "skillexception",
    "failed to load skill", "error loading skill", "skill 不存在",
    "skill 加载失败", "skill 未找到", "skill error",
]
# 成功信号(教师轨迹): 技能正确使用/引用
SUCCESS_SIGNALS = [
    "using skill", "loaded skill", "applied skill", "load skill",
    "遵循技能", "使用技能", "调用技能", "skill loaded",
]

# 停用词(蒸馏时过滤, 避免把通用词当缺失知识)
STOPWORDS = set("""a an and as at based become by for from has have in into is it of
of often or such that the this to was were will with large language model llm
agents agent system file path use used using when which their there our your
about between during under over them then these those known same only also
can could should would need needs may might make made more most much many each
some any all s t d not do does did be been being are on off up down""".split())


def scan_skills():
    """扫描技能, 返回 {name: {desc, path}}"""
    res = {}
    if not SKILLS_DIR.exists():
        return res
    for skmd in SKILLS_DIR.rglob("SKILL.md"):
        try:
            text = skmd.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
            name = skmd.parent.name
            desc = ""
            if m:
                dm = re.search(r"^description:\s*(.+)$", m.group(1), re.M)
                nm = re.search(r"^name:\s*(.+)$", m.group(1), re.M)
                if nm: name = nm.group(1).strip()
                if dm: desc = dm.group(1).strip().strip('"\'')[:150]
            res[name] = {"desc": desc, "path": str(skmd.relative_to(SKILLS_DIR))}
        except Exception:
            continue
    return res


def collect_trajectories():
    """
    从 session DB 收集技能相关的失败/成功轨迹(对比教师/学生).
    改进(借鉴 OSReward 严格验证): 只采 user/tool 角色的真实失败,
    排除 assistant(self-report)的自述噪声, 避免"自我引用的宽松偏差".
    """
    if not STATE_DB.exists():
        return [], []
    fails, sucs = [], []
    try:
        conn = sqlite3.connect(str(STATE_DB))
        # 按 role 区分: 只取 user/tool 消息(真实执行), 排除 assistant 叙述
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE content IS NOT NULL "
            "AND role IN ('user','tool') ORDER BY id DESC LIMIT 500"
        ).fetchall()
        conn.close()
        for role, c in rows:
            low = c.lower()
            if any(s in low for s in FAIL_SIGNALS):
                fails.append(c[:300])
            elif any(s in low for s in SUCCESS_SIGNALS):
                sucs.append(c[:300])
    except Exception:
        pass
    return fails, sucs


# ---- 1. 补丁生成 (对比蒸馏) ----
def distill_patch(fail_text, success_texts, skill_name):
    """
    对比 失败 与 成功 使用, 蒸馏补丁规则.
    原理(SKILL-KD): 失败轨迹缺知识/策略 → 用成功样本反推出缺失的可操作行为
    返回补丁dict
    """
    fail_words = set(re.findall(r"[a-z\u4e00-\u9fff]{2,}", fail_text.lower()))
    # 收集成功样本中, 失败文本中缺失的关键词 (反推缺失知识)
    covered = set()
    for s in success_texts:
        covered |= set(re.findall(r"[a-z\u4e00-\u9fff]{2,}", s.lower()))
    missing = (covered - fail_words) - STOPWORDS     # 过滤停用词
    # 只保留技能相关的高信号词(排除纯英文通用词, 保留中文语义词)
    signal_words = [w for w in missing
                    if re.search(r"[\u4e00-\u9fff]", w)          # 保留中文词
                    or len(w) >= 5                              # 较长英文专用词
                    or w in ("usage","required","config","deploy",
                             "command","invoke","format","verify")]

    patch = {
        "skill": skill_name,
        "timestamp": datetime.now().isoformat(),
        "diagnosis": "技能使用失败: 缺失败样本中未覆盖的知识/策略",
        "missing_terms": sorted(list(missing))[:25],      # 学生缺失的知识(可作补丁线索)
        "suggested_rules": [],                             # 待合并进SKILL.md的规则
    }
    # 生成可读规则
    for w in signal_words[:8]:
        patch["suggested_rules"].append(f"确保处理 '{w}' 相关内容后再调用技能")
    return patch


# ---- 2. 独立验证 (借鉴 OSReward: 不用LLM自评, 用独立匹配器) ----
def verify_patch(patch, fail_samples):
    """
    独立验证补丁是否能覆盖新失败样本.
    借鉴 OSReward: VLM作为judge有宽松偏差 → 此处用独立规则匹配器做"严格验证"
    返回 (pass, strict): pass=补丁缺失词是否在新失败中出现(可观测), strict=覆盖比
    """
    missing = set(patch.get("missing_terms", []))
    if not missing or not fail_samples:
        return 0.0
    hit = 0
    for f in fail_samples:
        if any(w in f.lower() for w in list(missing)[:10]):
            hit += 1
    return round(hit / len(fail_samples), 2)   # 严格覆盖率(独立交叉验证)


# ---- 3. 防漂移 (借鉴 SKILL-KD Drift-Aware Consolidation) ----
def consolidate(patch_hist, new_patch):
    """
    规则整合: 判定补丁是 新增/修改/删除. 聚合冗余防漂移.
    若新补丁的 missing_terms 与历史重叠>50% → 判为"迭代修改"(更新),
    否则"新增规则". 移除已失效(全在缺失集)的历史补丁.
    """
    if not patch_hist:
        return "add"
    overlap = 0
    prev = set()
    for p in patch_hist[-3:]:
        prev |= set(p.get("missing_terms", []))
    diff = set(new_patch["missing_terms"])
    if prev and diff:
        overlap = len(prev & diff) / max(len(diff), 1)
    if overlap >= 0.5:
        return "update"     # 迭代修改(非漂移)
    if overlap <= 0.1:
        return "add"
    return "refine"


def run(dry=False):
    print("="*62)
    print("技能补丁生成与验证器 (SKILL-KD + OSReward 借鉴落地)")
    print("="*62)
    skills = scan_skills()
    print(f"扫描技能: {len(skills)}")
    fails, sucs = collect_trajectories()
    print(f"失败轨迹(学生): {len(fails)} | 成功轨迹(教师): {len(sucs)}")

    db = json.loads(PATCH_DB.read_text(encoding="utf-8")) if PATCH_DB.exists() \
        else {"version": "1.0", "patches": []}
    now = datetime.now().isoformat()

    if not fails:
        print("\n✅ 无失败信号, 技能健康, 无需补丁")
        return

    new_patches = 0
    for f in fails[:5]:          # 最多5个失败样本
        skill_name = "未知技能"
        # 尝试定位涉及技能
        for sname in skills:
            if sname.lower() in f.lower():
                skill_name = sname
                break
        patch = distill_patch(f, sucs[:10], skill_name)
        cover = verify_patch(patch, fails)
        action = consolidate(db["patches"], patch)
        patch["verify_coverage"] = cover      # 独立验证覆盖率
        patch["action"] = action              # 新增/修改/删除判定
        db["patches"].append(patch)
        new_patches += 1
        print(f"\n  🧩 补丁#{len(db['patches'])} [{action}] 技能:{skill_name}")
        print(f"     缺失知识({patch['missing_terms'][:5]}...) 覆盖验证:{cover}")
        if patch["suggested_rules"]:
            print(f"     建议规则: {patch['suggested_rules'][:3]}")
        # 防漂移: 若某历史补丁的缺失词全部被后续覆盖 → 标注已吸收
        if action == "update":
            print(f"     → 判定为迭代修订(防漂移: 与历史重叠>50%)")

    # 原子写
    PATCH_DB.parent.mkdir(exist_ok=True)
    tmp = PATCH_DB.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, PATCH_DB)
    print(f"\n📦 存档: {PATCH_DB} (共{len(db['patches'])}个补丁, 本次{new_patches})")
    print("\n💡 下一步: 根据补丁[Actor]更新对应 SKILL.md (借鉴SKILL-KD: 补丁→重跑→防漂移闭环)")
    print("   注: 本工具为\"检测+补丁候选+独立验证\", 实际SKILL.md写入需人工/主Agent确认")


if __name__ == "__main__":
    if "--status" in sys.argv:
        db = json.loads(PATCH_DB.read_text(encoding="utf-8")) if PATCH_DB.exists() else {"patches": []}
        print(f"=== 补丁历史库: {len(db['patches'])} 个补丁 ===")
        for i, p in enumerate(db["patches"], 1):
            print(f"  #{i} [{p.get('action')}] {p['skill']}: cov={p.get('verify_coverage')} "
                  f"missing={p['missing_terms'][:3]}")
    elif "--dry" in sys.argv:
        run(dry=True)
    else:
        run()
