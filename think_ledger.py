# -*- coding: utf-8 -*-
"""J-Space 思维断点续传工具 (2026-08-16, GA3)
吸收: J-Space Suite jspace.py seam/resume (台账+断点续传)
用法: seam (保存当前思维状态) / resume (恢复)
台账: 不可信拒读 (LedgerReadError 对齐)
"""
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(os.path.dirname(BASE), "data", "think_ledger_v2.json")
MAX_HISTORY = 20  # 保留最后 20 版本 (防膨胀, 成本可控)


def seam(note, detail=""):
    """保存思维状态 (版本化: 追加历史, 不回滚覆盖)"""
    entry = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "note": note,
             "detail": detail}
    try:
        with open(LEDGER, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {"current": None, "history": []}
    data["history"].append(entry)
    data["history"] = data["history"][-MAX_HISTORY:]  # 截断保留 20
    data["current"] = entry
    with open(LEDGER, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return {"saved": LEDGER, "ts": entry["ts"], "note": note}


class LedgerReadError(Exception):
    """台账损坏: 不可信状态不如无状态 (J-Space 对齐)"""


def resume():
    """恢复思维状态 (续传, 版本化: 返回最近版本)"""
    if not os.path.exists(LEDGER):
        raise LedgerReadError("台账不存在 — 无状态可恢复")
    try:
        with open(LEDGER, encoding="utf-8") as f:
            data = json.load(f)
        entry = data.get("current") if isinstance(data, dict) else None
        if entry is None or "ts" not in entry:
            raise LedgerReadError("台账结构损坏")
        return entry
    except (json.JSONDecodeError, OSError) as e:
        raise LedgerReadError(f"台账不可读: {e}") from e


def clear():
    if os.path.exists(LEDGER):
        os.unlink(LEDGER)
    return {"cleared": True}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "seam":
        state = sys.argv[2] if len(sys.argv) > 2 else "研究/任务进行中"
        note = sys.argv[3] if len(sys.argv) > 3 else ""
        r = seam(state, note)
        print(f"✅ 断点已存: {r['note'] or r['state']} @ {r['ts']}")
    elif cmd == "resume":
        try:
            r = resume()
            print(f"🔄 恢复: [{r['ts']}] {r['note'] or ''}")
            print(f"  状态: {r.get('detail', r.get('state', ''))}")
            print("  → 继续执行 (seam 保存的上下文)")
        except LedgerReadError as e:
            print(f"❌ {e}")
    elif cmd == "clear":
        print(f"✅ {clear()}")
    else:
        print("用法: think_ledger.py seam '<状态>' [备注] | resume | clear")


if __name__ == "__main__":
    main()
