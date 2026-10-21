# -*- coding: utf-8 -*-
"""memory_guard 接入 /memory 审批 v1.0 (2026-08-10)
在 /memory approve 前调用 memory_guard 检查 → 拦截注入

接入点: hermes_cli/write_approval_commands.py _apply_one 之前
落地: 提供 wrapper, agent 审批时自动守护

用法:
  python memory_guard_approval.py check <content> [source]
  python memory_guard_approval.py batch <payload.json>
"""
import os, sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memory_guard import check

def guard_approval(content: str, source: str = "memory_file") -> dict:
    """审批前守护: 返回 {approved, reason}"""
    result = check(content, source)
    if result["risk_level"] in ("high", "medium"):
        return {
            "approved": False,
            "reason": f"注入风险 {result['risk_level']}: {result['findings']}",
            "detail": result,
        }
    return {"approved": True, "reason": "通过", "detail": result}

def guard_batch(payload: dict) -> dict:
    """批量操作守护 (add/replace/batch)"""
    action = payload.get("action", "")
    ops = []
    if action == "batch":
        ops = payload.get("operations", [])
    elif action in ("add", "replace"):
        ops = [payload]
    results = []
    for op in ops:
        content = op.get("content", "")
        target = op.get("target", "memory")
        verdict = guard_approval(content, f"memory_approve:{target}")
        results.append({"op": op.get("action", action), "target": target, **verdict})
    blocked = [r for r in results if not r["approved"]]
    return {
        "approved": len(blocked) == 0,
        "blocked_count": len(blocked),
        "results": results,
        "summary": f"{len(results)} 操作, {len(blocked)} 拦截" if blocked else f"{len(results)} 操作全部通过",
    }

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "check":
        r = guard_approval(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "memory_file")
        print(f"{'✅ 通过' if r['approved'] else '🛡️ 拦截'}: {r['reason']}")
    elif len(sys.argv) >= 3 and sys.argv[1] == "batch":
        payload = json.load(open(sys.argv[2], encoding="utf-8"))
        r = guard_batch(payload)
        print(f"{'✅ ' + r['summary'] if r['approved'] else '🛡️ ' + r['summary']}")
        for res in r["results"]:
            print(f"  {'✅' if res['approved'] else '🛡️'} [{res['op']}:{res['target']}] {res['reason']}")
    else:
        print("用法: memory_guard_approval.py check <content> [source] | batch <payload.json>")
