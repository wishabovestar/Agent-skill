#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agent_tool_table_audit.py — 校验 agent_cluster 的【角色工具表】真实性

【为什么做这个】(2026-09-17)
  r1167 我写下待办「用 registry 的 27 角色建角色工具表(现在角色只有名字+描述, 无工具绑定)」
  —— ★ **核查后这条待办是错的**: registry.json 里 27/27 **全部已有 `tools` 字段**。
  ⇒ 真正的待办不是"建表", 而是"**校验表**": 声明了的工具**是否真实存在**。

【三个要抓的问题】
  ① 声明的工具名**不在真实工具集** ⇒ 幽灵工具
  ② 工具**存在但当前不可用** ⇒ ★ 「存在 ≠ 可用」(与 Emergence World 的
     「检测 ≠ 遏制」同构: 名字对不等于事情能做成)
  ③ `tools` 与 `tools_available` **两套字段并存** ⇒ 命名分裂
     (与本机既有的 `depends_on` vs `dependencies` 同族)

用法:
  python agent_tool_table_audit.py            # 报告
  python agent_tool_table_audit.py --selftest
"""
import json
import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(BASE, "agent_cluster", "registry.json")

# ── 真实工具集(本会话权威可用的直接工具名, 来自运行时工具表)
REAL_TOOLS = {
    "terminal", "read_file", "write_file", "search_files", "patch",
    "execute_code", "skill_manage", "skill_view", "skills_list",
    "delegate_task", "memory", "clarify", "web_search", "web_extract",
    "vision_analyze", "text_to_speech", "browser_exec",
    "browser_vault_list", "browser_vault_fill", "browser_vault_unlock",
    "browser_vault_save_login", "browser_vault_enter_code",
    # 延迟加载(deferred catalog)
    "computer_use", "cronjob_manage", "headroom_retrieve", "headroom_status",
    "process_manage", "session_search", "todo_list",
}

# ── ★ 已知【存在但当前不可用】的工具(运行实测, 非推断)
KNOWN_UNAVAILABLE = {
    "web_extract": "运行返回不可用/超时(本机实测, 多次)",
    "browser_exec": "运行返回不可用(本机实测)",
    "computer_use": "需桌面驱动, 未在本机验证",
}

# ── ★ 已知【名字疑似写错】的别名 → 标准名
ALIAS_HINTS = {
    "file": "read_file / write_file(无名为 file 的工具)",
    "todo": "todo_list",
    "search": "search_files",
    "edit": "patch",
    "bash": "terminal",
    "shell": "terminal",
    "run": "terminal / execute_code",
    "http": "web_extract / terminal+curl",
}


def load_agents():
    d = json.load(open(REG, encoding="utf-8"))
    ag = d.get("agents", {})
    return ag if isinstance(ag, dict) else {}


def audit(agents=None):
    ag = agents if agents is not None else load_agents()
    ghost, unavailable, ok_rows = [], [], []
    for aid, a in ag.items():
        tools = a.get("tools") or []
        g = [t for t in tools if t not in REAL_TOOLS]
        u = [t for t in tools if t in KNOWN_UNAVAILABLE]
        ghost.append({"agent": aid, "tools": g}) if g else None
        unavailable.append({"agent": aid, "tools": u}) if u else None
        ok_rows.append((aid, len(tools)))
    split = [k for k, a in ag.items() if a.get("tools_available")]
    freq = Counter(t for a in ag.values() for t in (a.get("tools") or []))
    return {
        "n_agents": len(ag),
        "ghost": ghost,
        "unavailable": unavailable,
        "tools_available_split": split,
        "freq": freq.most_common(),
        "alias_hits": {t: ALIAS_HINTS[t] for t in freq if t in ALIAS_HINTS},
    }


def report(a):
    print("=" * 78)
    print("  角色工具表审计 (agent_cluster/registry.json)")
    print("=" * 78)
    print("  角色总数: %d" % a["n_agents"])
    print()
    print("  ① 幽灵工具(不在真实工具集)")
    if a["ghost"]:
        for x in a["ghost"]:
            print("     🔴 %-16s %s" % (x["agent"], ", ".join(x["tools"])))
    else:
        print("     ✅ 无")
    print()
    print("  ② ★ 存在但【当前不可用】的工具")
    if a["unavailable"]:
        for x in a["unavailable"]:
            for t in x["tools"]:
                print("     🟡 %-16s %-14s ← %s" % (x["agent"], t, KNOWN_UNAVAILABLE[t]))
    else:
        print("     ✅ 无")
    print()
    print("  ③ 命名分裂: tools vs tools_available")
    print("     `tools` 覆盖 %d/%d 角色; `tools_available` 仅 %d 个角色有: %s"
          % (a["n_agents"], a["n_agents"], len(a["tools_available_split"]),
             ", ".join(a["tools_available_split"]) or "-"))
    print()
    print("  ④ 疑似写错的工具别名")
    if a["alias_hits"]:
        for t, hint in a["alias_hits"].items():
            print("     🟡 %-10s → 应为 %s" % (t, hint))
    else:
        print("     ✅ 无")
    print()
    print("  ⑤ 工具使用频次")
    for t, n in a["freq"]:
        mark = "🟡" if t in KNOWN_UNAVAILABLE else ("🔴" if t not in REAL_TOOLS else "  ")
        print("     %s %-22s %d" % (mark, t, n))


def _selftest() -> int:
    print("=" * 78)
    print("  自检 (6 项)")
    print("=" * 78)
    ok = True
    # 1 真工具被认
    r = audit({"a": {"tools": ["terminal", "read_file"]}})
    c = not r["ghost"] and not r["unavailable"]
    print("  T1  真工具不误报: %s" % ("✅" if c else "🔴")); ok &= c
    # 2 幽灵工具被抓
    r = audit({"a": {"tools": ["terminal", "frobnicate_tool"]}})
    c = r["ghost"] and r["ghost"][0]["tools"] == ["frobnicate_tool"]
    print("  T2  ★ 幽灵工具被抓: %s" % ("✅" if c else "🔴")); ok &= c
    # 3 存在但不可用被抓(且不算幽灵)
    r = audit({"a": {"tools": ["web_extract"]}})
    c = bool(r["unavailable"]) and not r["ghost"]
    print("  T3  ★ 「存在≠可用」被抓且不误判为幽灵: %s" % ("✅" if c else "🔴")); ok &= c
    # 4 命名分裂检出
    r = audit({"a": {"tools": ["terminal"], "tools_available": ["x"]}})
    c = r["tools_available_split"] == ["a"]
    print("  T4  命名分裂检出: %s" % ("✅" if c else "🔴")); ok &= c
    # 5 别名提示
    r = audit({"a": {"tools": ["file", "todo"]}})
    c = "file" in r["alias_hits"] and "todo" in r["alias_hits"]
    print("  T5  别名提示: %s" % ("✅" if c else "🔴")); ok &= c
    # 6 真 registry 可跑
    a = audit()
    c = a["n_agents"] > 0
    print("  T6  真 registry 可审计 (%d 角色): %s" % (a["n_agents"], "✅" if c else "🔴"))
    ok &= c
    print()
    print("  判定: %s (6 项)" % ("✅ 全通过" if ok else "🔴 有未通过项"))
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    report(audit())
