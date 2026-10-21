#!/usr/bin/env python3
"""
① 工具集门控 — Multi-Level Toolset Gating
===========================================
Strategy: 按6功能域分组，运行时仅加载核心+当前域的工具

当前CLI: 48工具 × 250 tok = 12,000 tok/请求，仅5个被使用(90%浪费)
当前微信: 15工具 × 250 tok = 3,750 tok/请求，仅5个被使用(67%浪费)

方案: 分层门控
  - L0 Core (always): terminal, file, web, delegation, memory, session_search, clarify, todo, cronjob, skills
  - L1 Research (on-demand): vision, browser, video
  - L2 Creative (on-demand): image_gen, video_gen
  - L3 Dev (on-demand): code_execution, kanban, computer_use
  - L4 Extra (on-demand): x_search, video_gen extras

每组间开关不影响其他组。默认仅L0活跃。

本脚本作用:
  1. 展示当前工具浪费
  2. 更新platform_toolsets配置（L0默认+扩展按需）
  3. 验证配置后的工具数量
"""

import json
import sys

# =========================================================
# Phase 1: 分析当前工具浪费
# =========================================================
def analyze_tool_waste():
    """计算当前各域的工具定义Token浪费"""
    
    # 六域分类 (按功能)
    tool_domains = {
        "L0_core": [
            "web_search", "web_extract",
            "terminal", "process",
            "read_file", "write_file", "patch", "search_files",
            "delegate_task", "execute_code",
            "memory",
            "session_search",
            "clarify",
            "todo",
            "cronjob",
            "skills_list", "skill_view", "skill_manage",
            "text_to_speech",
        ],
        "L1_research": [
            "vision_analyze",
            "browser_navigate", "browser_snapshot", "browser_click",
            "browser_type", "browser_scroll", "browser_back",
            "browser_press", "browser_get_images", "browser_vision",
            "browser_console", "browser_cdp", "browser_dialog",
            "video_analyze",
        ],
        "L2_creative": [
            "image_generate",
            "video_generate", "xai_video_edit", "xai_video_extend",
        ],
        "L3_devops": [
            "kanban_show", "kanban_list", "kanban_complete",
            "kanban_block", "kanban_heartbeat", "kanban_comment",
            "kanban_create", "kanban_link", "kanban_unblock",
            "computer_use",
        ],
        "L4_special": [
            "x_search",
        ],
        "L5_extra": [
            "read_terminal", "close_terminal",
            "browser_cdp", "browser_dialog",
            "ha_list_entities", "ha_get_state", "ha_list_services", "ha_call_service",
        ],
    }
    
    print("=" * 65)
    print(" ① 工具集门控 — 工具域分组")
    print("=" * 65)
    
    total_current = 0
    total_optimized = 0
    total_domains = 0
    
    for domain, tools in tool_domains.items():
        tokens = len(tools) * 250
        is_core = "L0" in domain
        label = "✅ CORE" if is_core else "🔲 EXTRA"
        print(f"\n  {label} {domain}:")
        print(f"       {len(tools):2d} tools x 250 tok = ~{tokens:>5,} tok")
        for t in tools[:6]:
            print(f"       · {t}")
        if len(tools) > 6:
            print(f"       · ...+{len(tools)-6} more")
        if is_core:
            total_optimized += tokens
        total_current += tokens
        total_domains += len(tools)
    
    print(f"\n  ├─ 当前(全量):  {total_current:,} tok ({total_domains} tools)")
    print(f"  ├─ 优化后(L0): {total_optimized:,} tok ({sum(len(t) for n,t in tool_domains.items() if 'L0' in n)} tools)")
    print(f"  └─ 节省:       {total_current - total_optimized:,} tok/请求 ({(total_current-total_optimized)/total_current*100:.0f}%)")
    
    return tool_domains


# =========================================================
# Phase 2: 生成更新的platform_toolsets配置
# =========================================================
def generate_config_suggestion():
    """输出更新的platform_toolsets配置块"""
    
    update = {
        "platform_toolsets": {
            "cli": [
                # L0 Core — 日常必需的通用工具
                "terminal", "file", "web",
                "delegation", "memory", "session_search",
                "clarify", "todo", "cronjob",
                "skills",
                # L1-L5按需启用（通过`hermes tools`开关）
                # 以下为注释参考，不默认启用：
                # "vision", "browser", "video",        # L1 Research
                # "image_gen", "video_gen",              # L2 Creative
                # "kanban", "computer_use",              # L3 DevOps
                # "x_search",                             # L4 Special
                # "tts" → 已包含在core中
            ],
            "weixin": [
                "terminal", "file", "web",
                "delegation", "memory", "session_search",
                "clarify", "todo", "cronjob",
            ],
        }
    }
    
    print(f"\n\n  ┌─ 推荐配置更新 ─────────────────────────────────┐")
    print(f"  │ 将 platform_toolsets.cli 改为以下值，实现L0门控 │")
    print(f"  └────────────────────────────────────────────────┘")
    print()
    print(json.dumps(update, indent=2, ensure_ascii=False))
    print()
    
    # 按域分组的等效工具数量
    core_tools = [
        "terminal", "process",
        "read_file", "write_file", "patch", "search_files",
        "web_search", "web_extract",
        "delegate_task", "execute_code",
        "memory", "session_search",
        "clarify", "todo", "cronjob",
        "skills_list", "skill_view", "skill_manage",
        "text_to_speech",
    ]
    
    print(f"  L0 Core 工具数: {len(core_tools)}")
    print(f"  L0 Core Token: ~{len(core_tools)*250:,}/请求")
    print(f"  相对CLI当前({48})节省: ~{(48-len(core_tools))*250:,} tok/请求 ({(48-len(core_tools))/48*100:.0f}%)")
    return update


# =========================================================
# Phase 3: 验证脚本 — 检查当前配置
# =========================================================
def verify_current_config(config_path=None):
    """读取当前config.yaml中的platform_toolsets"""
    import os
    if config_path is None:
        config_path = r"D:\hermes\hermes-data\profiles\mybot\config.yaml"
    
    if not os.path.exists(config_path):
        print(f"\n  ❌ 找不到配置: {config_path}")
        return None
        
    print(f"\n\n  📄 当前配置 ({config_path}):")
    with open(config_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    in_section = False
    for i, line in enumerate(lines):
        if 'platform_toolsets:' in line:
            in_section = True
        if in_section:
            print(f"    {line.rstrip()}")
            if in_section and line.strip() and not line[0].isspace():
                # new top-level key
                if 'platform_toolsets' not in line:
                    in_section = False
    
    return config_path


if __name__ == "__main__":
    analyze_tool_waste()
    generate_config_suggestion()
    verify_current_config()
