#!/usr/bin/env python3
"""pre_tool_call 守卫：拦截「解析后仍不可用」的工具调用，并留审计台账。

Hermes 核心已覆盖的两件事（本 hook 不重复）：
  · 非法 JSON / 参数未以 } 或 ] 结尾的截断 ⇒ agent/turn_tool_validation.py 已拒绝执行
  本 hook 补的是核心没覆盖的两类：
  1) 参数里残留 DSML 标记（<｜DSML｜）⇒ 解析器「尽量解析」的半成品，语义不可信
  2) tool_input 不是对象（列表/字符串/None）⇒ 下游按 dict 取值必炸

协议（agent/shell_hooks.py）：
  stdin  JSON {hook_event_name, tool_name, tool_input|args, session_id, cwd, extra}
  exit 2 = 阻断（stderr 作为阻断原因）
  其它 = 放行；任何内部异常一律放行（fail-open），但异常写入台账
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone

LEDGER = os.environ.get(
    "TOOL_GUARD_LEDGER",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "cache", "tool_guard", "ledger.jsonl"),
)
BLOCK_MARKERS = ("<｜DSML｜", "｜DSML｜")
WARN_MARKERS = ("⟪",)  # Hermes 上下文压缩残留标记：只记不拦


def _iter_strings(obj, path="$"):
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _iter_strings(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _iter_strings(v, f"{path}[{i}]")


def judge(tool_name: str, args) -> tuple[str, str]:
    """返回 (verdict, reason)，verdict ∈ BLOCK / WARN / OK。"""
    if not isinstance(args, dict):
        return "BLOCK", f"tool_input 不是对象（{type(args).__name__}），下游按 dict 取值会失败"
    bar = chr(0xFF5C)  # 全角竖线，用码位构造，源码不出现字面标记
    markers = ("<" + bar + "DSML" + bar, bar + "DSML" + bar)
    for path, s in _iter_strings(args):
        stripped = s.lstrip()
        for m in markers:
            if stripped.startswith(m):
                return "BLOCK", (f"参数 {path} 以 DSML 工具调用块开头 —— 解析器把整块当成了参数值，"
                                 f"语义不可信；请重新生成完整参数")
    warns = [f"{p} 含压缩残留标记" for p, s in _iter_strings(args)
             if any(m in s for m in WARN_MARKERS)]
    if not args:
        warns.append("参数为空对象 {}")
    if warns:
        return "WARN", "; ".join(warns)
    return "OK", ""


LEDGER_MAX_BYTES = int(os.environ.get("TOOL_GUARD_LEDGER_MAX", "2000000"))
LEDGER_KEEP = int(os.environ.get("TOOL_GUARD_LEDGER_KEEP", "3"))
SLOW_MARKER = LEDGER + ".slow"
SLOW_COOLDOWN_S = 600
# 单次追加的硬时限：超时说明磁盘/杀软在拖，后续 10 分钟不再写台账，
# 以「丢台账」换「不拖慢每一次工具调用」（框架侧 pre_tool_call 超时是 fail-closed）。
APPEND_DEADLINE_S = 0.30


def _rotated_path(idx: int) -> str:
    return f"{LEDGER}.{idx}"


def _rotate_if_needed() -> None:
    try:
        size = os.path.getsize(LEDGER)
    except OSError:
        return
    if size < LEDGER_MAX_BYTES:
        return
    try:
        oldest = _rotated_path(LEDGER_KEEP)
        if os.path.exists(oldest):
            os.remove(oldest)
        for i in range(LEDGER_KEEP - 1, 0, -1):
            src, dst = _rotated_path(i), _rotated_path(i + 1)
            if os.path.exists(src):
                os.replace(src, dst)
        os.replace(LEDGER, _rotated_path(1))
    except OSError:
        pass  # 轮转失败也不能阻断工具；下次再试


def _in_slow_cooldown() -> bool:
    try:
        return (time.time() - os.path.getmtime(SLOW_MARKER)) < SLOW_COOLDOWN_S
    except OSError:
        return False


def _mark_slow(err: str) -> None:
    try:
        os.makedirs(os.path.dirname(SLOW_MARKER), exist_ok=True)
        with open(SLOW_MARKER, "w", encoding="utf-8") as fh:
            fh.write(f"{datetime.now(timezone.utc).isoformat()}\t{err[:200]}\n")
    except OSError:
        pass


def _append(record: dict) -> None:
    if _in_slow_cooldown():
        return
    t0 = time.perf_counter()
    try:
        os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
        _rotate_if_needed()
        with open(LEDGER, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001 — 台账写不进去不能反过来阻断工具
        _mark_slow(f"write failed: {exc}")
    else:
        if time.perf_counter() - t0 > APPEND_DEADLINE_S:
            _mark_slow(f"append took {time.perf_counter() - t0:.2f}s")


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001
        return 0
    if not isinstance(payload, dict):
        return 0
    tool = str(payload.get("tool_name") or payload.get("name") or "")
    args = payload.get("tool_input", payload.get("args", {}))
    try:
        verdict, reason = judge(tool, args)
    except Exception:  # noqa: BLE001
        _append({"ts": datetime.now(timezone.utc).isoformat(), "tool": tool, "verdict": "ERROR",
                 "reason": traceback.format_exc(limit=3)[-500:]})
        return 0
    _append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "verdict": verdict,
        "reason": reason,
        "session_id": payload.get("session_id"),
        "arg_keys": sorted(args) if isinstance(args, dict) else None,
        "arg_bytes": len(json.dumps(args, ensure_ascii=False)) if args is not None else 0,
    })
    if verdict == "BLOCK":
        sys.stderr.write(f"[tool_guard] 拒绝执行 {tool}: {reason}\n")
        return 2
    return 0


def selftest() -> int:
    cases = [
        ("OK", {"tool_name": "terminal", "tool_input": {"command": "ls"}}),
        ("BLOCK", {"tool_name": "terminal", "tool_input": {
            "command": '<｜DSML｜ calls><｜DSML｜ invoke name="x">'}}),
        ("BLOCK", {"tool_name": "terminal", "tool_input": ["not", "a", "dict"]}),
        ("WARN", {"tool_name": "read_file", "tool_input": {}}),
    ]
    bad = 0
    for expect, payload in cases:
        v, why = judge(payload["tool_name"], payload["tool_input"])
        ok = v == expect
        bad += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] expect={expect} got={v} :: {why[:80]}")
    print(f"RESULT: {'OK' if not bad else 'FAIL'} ({bad} 个不符)")
    return 0 if not bad else 3


def status() -> int:
    rows = [f"ledger={LEDGER}", f"max_bytes={LEDGER_MAX_BYTES} keep={LEDGER_KEEP}"]
    for path in [LEDGER] + [_rotated_path(i) for i in range(1, LEDGER_KEEP + 1)]:
        try:
            st = os.stat(path)
            rows.append(f"  {os.path.basename(path)}: {st.st_size} B  {datetime.fromtimestamp(st.st_mtime):%Y-%m-%d %H:%M:%S}")
        except OSError:
            rows.append(f"  {os.path.basename(path)}: (不存在)")
    if _in_slow_cooldown():
        rows.append(f"SLOW 冷却中（剩余 {SLOW_COOLDOWN_S - int(time.time() - os.path.getmtime(SLOW_MARKER))}s）")
        rows.append(f"  原因: {open(SLOW_MARKER, encoding='utf-8').read().strip()}")
    else:
        rows.append("SLOW 标记: 无")
    print("\n".join(rows))
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    if "--status" in sys.argv:
        raise SystemExit(status())
    raise SystemExit(main())

