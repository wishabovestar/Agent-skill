#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_agent_tools.py — 修正 agent_cluster/registry.json 的工具表

【依据】agent_tool_table_audit.py 的审计结果 + 逐条语境核实
  · coder.tools          含 'file'  且与 read_file/write_file 并存 ⇒ 冗余, 删除
  · analyst.tools        含 'file'  同上 ⇒ 删除
  · project_manager.tools 含 'todo' (真实工具名是 todo_list) ⇒ 改名
  · 'tools_available' 字段: 名字像工具, 内容实为【能力标签】(coder: benchmark/profiling)
    ⇒ ★ 不删数据, 只【在 registry 顶层加一条字段语义说明】, 避免后人再误解

★ 只动这几个明确的点; 其余保持原样. 先备份再改.
"""
import io
import json
import os
import shutil
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = r"D:\hermes\hermes-data\profiles\qqbot3"
REG = os.path.join(BASE, "agent_cluster", "registry.json")

# (agent, 删除的工具, 重命名的 {旧:新})
FIX_DELETE = {"coder": ["file"], "analyst": ["file"]}
FIX_RENAME = {"project_manager": {"todo": "todo_list"}}
SEMANTIC_NOTE = ("tools = 真实工具名(须存在于运行时工具集); "
                 "tools_available = 【能力/专长标签】, 不是工具名 —— 勿混用")


def main() -> int:
    apply = "--apply" in sys.argv
    d = json.load(io.open(REG, encoding="utf-8"))
    ag = d["agents"]
    plan = []

    for aid, drop in FIX_DELETE.items():
        cur = ag[aid].get("tools") or []
        nw = [t for t in cur if t not in drop]
        if len(nw) != len(cur):
            plan.append("  %-16s 删除 %s" % (aid, drop))
            if apply:
                ag[aid]["tools"] = nw

    for aid, mp in FIX_RENAME.items():
        cur = ag[aid].get("tools") or []
        nw = [mp.get(t, t) for t in cur]
        if nw != cur:
            plan.append("  %-16s 重命名 %s" % (aid, mp))
            if apply:
                ag[aid]["tools"] = nw

    # 字段语义说明(顶层, 不动任何角色数据)
    note_key = "_field_semantics"
    if d.get(note_key) != SEMANTIC_NOTE:
        plan.append("  顶层           加 _field_semantics 说明")
        if apply:
            d[note_key] = SEMANTIC_NOTE

    if not plan:
        print("  无需修改")
        return 0
    print("  计划:")
    for p in plan:
        print(p)

    if not apply:
        print("\n  (干跑; 加 --apply 生效)")
        return 0

    bak = REG + ".bak_" + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(REG, bak)
    print("\n  备份: %s" % os.path.basename(bak))
    d["updated"] = int(time.time())
    io.open(REG, "w", encoding="utf-8", newline="\n").write(
        json.dumps(d, ensure_ascii=False, indent=2))
    print("  已写入 %s" % REG)

    # 复核
    d2 = json.load(io.open(REG, encoding="utf-8"))
    print("  复核 coder.tools           :", d2["agents"]["coder"]["tools"])
    print("  复核 analyst.tools         :", d2["agents"]["analyst"]["tools"])
    print("  复核 project_manager.tools :", d2["agents"]["project_manager"]["tools"])
    print("  复核 角色数(应仍为 27)     :", len(d2["agents"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
