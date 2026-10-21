# -*- coding: utf-8 -*-
"""CortexMem 体系总控 — herdr 组件集成 v1.0 (2026-08-11)
统一接入 herdr 借鉴组件到 CortexMem 记忆体系

组件:
  state_runtime   → 状态/运行时分离 (核心重构)
  handoff_session → 长任务断点保护
  blocked_board   → 任务阻塞看板
  agent_resume    → 会话引用恢复
  review_pane     → 代码审查窗格
  cron_guard      → cron 任务保护

用法:
  python cortexmem_hub.py --status      # 全组件状态
  python cortexmem_hub.py --guard <cmd> # 受保护执行
  python cortexmem_hub.py --review <repo> # 审查
  python cortexmem_hub.py --session <id>  # 会话恢复
"""
# side_effects: [写数据文件]
import os, sys, io, json, datetime

# stdout 重配放 __main__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 组件注册表 (统一管理)
COMPONENTS = {
    "cortexmem": {"script": "cortexmem.py", "desc": "核心记忆库 (三层图+三态+双路检索)", "active": True},
    "cortexmem_tool": {"script": "cortexmem_tool.py", "desc": "agent JSON 接口", "active": True},
    "cortexmem_guard": {"script": "cortexmem_guard.py", "desc": "安全防御 (memory_guard)", "active": True},
    "cortexmem_integrate": {"script": "cortexmem_integrate.py", "desc": "增量摄取 (state.db)", "active": True},
    "cortexmem_daily": {"script": "cortexmem_daily.py", "desc": "每日巩固 (同步+睡眠)", "active": True},
    "cortexmem_ab_test": {"script": "cortexmem_ab_test.py", "desc": "新旧 A/B 对比", "active": True},
    # ── herdr 借鉴组件 ──
    "state_runtime": {"script": "state_runtime.py", "desc": "herdr: State/Runtime 分离", "active": True},
    "handoff_session": {"script": "handoff_session.py", "desc": "herdr: 会话断点恢复", "active": True},
    "blocked_board": {"script": "blocked_board.py", "desc": "herdr: 阻塞看板", "active": True},
    "agent_resume": {"script": "agent_resume.py", "desc": "herdr: 会话引用 (id/path)", "active": True},
    "review_pane": {"script": "review_pane.py", "desc": "herdr: 审查窗格", "active": True},
    "cron_guard": {"script": "cron_guard.py", "desc": "herdr: cron 任务保护", "active": True},
}


def check_component(name: str, comp: dict) -> dict:
    """检查组件文件存在 + 大小"""
    path = os.path.join(BASE, "scripts", comp["script"])
    if os.path.exists(path):
        size = os.path.getsize(path)
        return {"name": name, "ok": True, "size": size, "desc": comp["desc"]}
    return {"name": name, "ok": False, "size": 0, "desc": comp["desc"]}


def status():
    print("═" * 60)
    print(f"🧠 CortexMem 体系总控 ({datetime.date.today()})")
    print("═" * 60)
    results = []
    for name, comp in COMPONENTS.items():
        r = check_component(name, comp)
        results.append(r)
        mark = "✅" if r["ok"] else "❌"
        size = f"({r['size']/1024:.1f}KB)" if r["ok"] else ""
        print(f"  {mark} {name}: {r['desc']} {size}")
    ok_count = sum(1 for r in results if r["ok"])
    print(f"\n📊 {ok_count}/{len(results)} 组件就绪")
    return {"ok": ok_count, "total": len(results)}


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if "--status" in sys.argv or len(sys.argv) == 1:
        status()
    elif "--guard" in sys.argv:
        # 受保护执行: cron_guard 包装
        from cron_guard import run_guarded
        i = sys.argv.index("--guard")
        cmd = sys.argv[i+1]
        task = sys.argv[i+2] if len(sys.argv) > i+2 else "guard-task"
        result = run_guarded(task, cmd, 300)
        print(json.dumps(result, ensure_ascii=False))
    elif "--review" in sys.argv:
        from review_pane import ReviewPane
        i = sys.argv.index("--review")
        pane = ReviewPane()
        r = pane.get_diff(sys.argv[i+1])
        print(json.dumps(r, ensure_ascii=False, default=str))
    elif "--session" in sys.argv:
        from handoff_session import HandoffSession
        i = sys.argv.index("--session")
        s = HandoffSession.load(sys.argv[i+1])
        print(json.dumps(s.summary() if s else {"error": "not found"}))
    else:
        print("用法: --status | --guard <cmd> [任务名] | --review <repo> | --session <id>")


if __name__ == "__main__":
    main()
