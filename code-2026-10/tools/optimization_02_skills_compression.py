#!/usr/bin/env python3
"""
② 技能层次压缩 — Skills Hierarchy Compression
=============================================
Strategy: 非核心技能分类→names-only（保留名称，去掉描述），
          核心/常加载技能保持完整描述

当前: 45技能 × 平均~26字描述 = ~1,172 tokens 的技能描述块
优化: 去除非核心类目的描述 → ~300 tokens（压缩~74%）

方案: 默认压缩"agent-*"、"3d-*"、"audio-*"等非核心分类，
      保留"difficulty-triage"、"profile-aware"等常加载技能的描述
"""

import json

# =========================================================
# Phase 1: 技能分类分析
# =========================================================

# 按使用频率和场景分类
SKILL_CATEGORIES = {
    # 🔵 核心 - 高频使用，保留完整描述
    "core": {
        "categories": [
            "difficulty-triage",    # 每会话必加载
            "profile-aware",        # 每会话必加载
            "network-resilience",   # 高频网络回退
            "security-sandbox",     # 安全层
            "hermes-agent",         # Hermes配置
            "systematic-debugging", # 调试工作流
            "codebase-research",    # 代码研究
            "plan",                 # 规划模式
            "spike",               # 技术验证
        ],
        "keep_full": True,
    },
    
    # 🔵 领域 - 根据当前场景保留
    "domain_battery": {
        "categories": [
            "battery-materials-research",
            "pdf-reader",
            "drawing-privacy-guard",
            "engineering-drawing-ocr",
            "ocr-and-documents",
            "visual-learning",
        ],
        "keep_full": False,  # 按场景切换
    },
    
    # ⚪ 非核心 - 默认names-only
    "non_core": {
        "categories": [
            "3d-model-agent",
            "agent-breacher",
            "agent-codeguardian",
            "agent-communicator",
            "agent-dispatcher",
            "agent-fortify",
            "agent-logician",
            "agent-tinglan",
            "agent-cluster-orchestrator",
            "algorithm-architect",
            "audio-transcription-agent",
            "audit-team",
            "autonomous-ai-agents",
            "chinese-news-search",
            "data-image-encoding",
            "data-privacy",
            "data-science",
            "devops",
            "excel-data-automation-workflow",
            "hermes-agent-skill-authoring",
            "hermes-performance-analysis",
            "knowledge-graph",
            "multi-user-profiling",
            "network-executor",
            "python-ocr-pipeline",
            "requesting-code-review",
            "self-improving-agent",
            "self-reinforcement",
            "simplify-code",
            "social-security-policy-advisor",
            "technical-research-survey",
            "test-driven-development",
            "weixin-qq-multiuser",
        ],
        "keep_full": False,
    },
}

# =========================================================
# Phase 2: 生成技能块大小对比
# =========================================================
def calculate_savings():
    """计算技能描述压缩的Token节省"""
    
    # 从实际文件中读取技能描述
    from pathlib import Path
    
    skills_dir = Path(r"D:\hermes\hermes-data\profiles\mybot\skills")
    
    # 技能名 → 描述映射
    skill_desc = {}
    skill_category = {}  # 技能名 → 分类
    
    # 建立反向映射: 技能名 → 所属大分类
    name_to_group = {}
    for group_name, group in SKILL_CATEGORIES.items():
        for cat in group["categories"]:
            # 这是技能名而不是分类名
            name_to_group[cat] = group_name
    
    # 读取实际SKILL.md中的描述
    for skill_file in sorted(skills_dir.rglob("SKILL.md")):
        content = skill_file.read_text(encoding="utf-8", errors="replace")
        rel = skill_file.relative_to(skills_dir)
        # 技能名 = 文件名(去掉SKILL.md)或者父目录
        # 实际上是：skills/category/SKILL.md 或 skills/SKILL.md
        # 我们的技能在 skills/<category>/SKILL.md
        category_name = rel.parent.name  # e.g., "difficulty-triage"
        
        desc = ""
        name = category_name
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                fm_text = content[3:end]
                # Simple yaml parsing without yaml module
                for line in fm_text.strip().split('\n'):
                    if line.strip().startswith('description:'):
                        desc = line.split(':', 1)[1].strip().strip("'\"")
                    elif line.strip().startswith('name:'):
                        name = line.split(':', 1)[1].strip().strip("'\"")
        
        # 确定分组
        group = name_to_group.get(name, "unclassified")
        skill_desc[name] = {
            "desc": desc,
            "desc_chars": len(desc),
            "desc_tokens": len(desc) // 4,
            "category": category_name,
            "group": group,
            "names_only": group in ("non_core", "unclassified") or (
                group == "domain_battery"  # 电池类按上下文开关，默认关闭
            ),
        }
    
    if not skill_desc:
        print("  ❌ 未找到技能文件")
        return
    
    print("=" * 65)
    print(" ② 技能层次压缩 — 技能描述Token对比")
    print("=" * 65)
    
    total_full = 0
    total_compact = 0
    per_skill_data = []
    
    for name in sorted(skill_desc.keys()):
        info = skill_desc[name]
        full_tok = info["desc_tokens"]
        # names-only format: "    - name: ..." → just name
        name_only_chars = len(f"    - {name}")  # no description
        compact_tok = name_only_chars // 4
        
        if info["names_only"]:
            total_full += full_tok
            total_compact += compact_tok
        else:
            total_full += full_tok
            total_compact += full_tok
        
        marker = "🟢" if not info["names_only"] else "🔘"
        comp_str = f"{compact_tok:>3} tok" if info["names_only"] else f"{full_tok:>3} tok 🔄"
        print(f"  {marker} {name:35s} full: {full_tok:>4} tok → {comp_str}")
    
    overhead_full = total_full + 700  # +700 for wrapper text + category headers
    overhead_compact = total_compact + 500
    
    print(f"\n  ├─ 当前(全描述): {overhead_full:,} tok")
    print(f"  ├─ 优化后(压缩): {overhead_compact:,} tok")
    print(f"  └─ 节省:        {overhead_full - overhead_compact:,} tok/请求 ({(overhead_full-overhead_compact)/overhead_full*100:.0f}%)")
    
    return skill_desc


# =========================================================
# Phase 3: 生成config.yaml新增配置块
# =========================================================
def generate_config_chunk():
    """输出config.yaml需要添加的skills.compact_categories配置"""
    
    # 所有非核心分类名
    non_core_cats = SKILL_CATEGORIES["non_core"]["categories"]
    
    config_snippet = f"""# 技能索引压缩 (优化②)
# 以下分类的技能在索引中仅显示名称(无描述)，节省~70% Token
# 任何技能仍可通过 skill_view(name) 正常加载
skills:
  compact_categories:
    - {non_core_cats[0]}
    # ... 共{len(non_core_cats)}个分类
    
# 若需按平台区分压缩策略:
# platform_compact_categories:
#   cli: [...]
#   weixin: [...]
"""

    print(f"\n\n  ┌─ 配置更新 ──────────────────────────────────┐")
    print(f"  │ (需要patch system_prompt.py以支持此配置)    │")
    print(f"  └─────────────────────────────────────────────┘")
    print(config_snippet)
    
    return non_core_cats


# =========================================================
# Phase 4: 生成system_prompt.py补丁
# =========================================================
def generate_patch():
    """输出对system_prompt.py的补丁"""
    
    patch = '''
# === PATCH: Skills config-driven compaction (优化②) ===
# 在 _compact_cats 计算后，追加从配置读取的额外压缩分类
_config_compact = frozenset()
try:
    from hermes_cli.config import get_config
    cfg = get_config()
    compact_from_cfg = cfg.get("skills", {}).get("compact_categories", [])
    if compact_from_cfg:
        # 把配置中的技能名→分类名映射
        # 因为compact_categories接受的是category name(skills父目录)
        # 但技能名和分类名相同（每分类一个技能）
        _config_compact = frozenset(compact_from_cfg)
except Exception:
    pass

_compact_cats = _compact_cats | _config_compact
'''
    print(f"\n  system_prompt.py 补丁:")
    print(patch)


if __name__ == "__main__":
    calculate_savings()
    generate_config_chunk()
    generate_patch()
