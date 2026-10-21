#!/usr/bin/env python3
"""tool_call_guard — 校验 LLM 工具调用参数是否为合法 JSON（含 DSML 残留检测）。

背景：deepseek-recipe 的 StreamProcessor 会把不完整的 DSML 块「尽量解析」，
截断时仍返回 finish_reason=tool_calls，但 arguments 可能是 '{"city": "Bei'。
下游若不校验，会拿到半截参数直接执行。

用法：
  python tool_call_guard.py <response.json> [...]
  python tool_call_guard.py --json '{"choices":[...]}'
退出码：0 = 全部通过；3 = 存在不可用工具调用（显式失败，不静默）
"""
from __future__ import annotations

import argparse
import json
import sys

DSML_MARKERS = ("<｜DSML｜", "＜｜DSML｜", "DSML｜")


def _iter_tool_calls(doc: dict):
    """按 OpenAI / Anthropic / Responses 三种协议抽取工具调用。"""
    for ch in doc.get("choices") or []:
        msg = ch.get("message") or {}
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            yield "chat.completions", fn.get("name"), fn.get("arguments")
    for block in doc.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            yield "messages", block.get("name"), block.get("input")
    for item in doc.get("output") or []:
        if isinstance(item, dict) and item.get("type") == "function_call":
            yield "responses", item.get("name"), item.get("arguments")


def check(doc: dict, source: str = "") -> list[tuple[str, str, str]]:
    """返回 [(level, name, detail)]，level ∈ PASS/WARN/FAIL。"""
    rows: list[tuple[str, str, str]] = []
    calls = list(_iter_tool_calls(doc))
    if not calls:
        rows.append(("PASS", "-", "无工具调用（nothing to validate）"))
        return rows
    for proto, name, args in calls:
        if isinstance(args, dict):
            raw = json.dumps(args, ensure_ascii=False)
            parsed = args
        else:
            raw = args if isinstance(args, str) else repr(args)
            parsed = None
            try:
                parsed = json.loads(raw)
            except Exception as exc:  # noqa: BLE001
                rows.append(("FAIL", f"{proto}:{name}", f"arguments 不是合法 JSON（{exc.__class__.__name__}: {exc}）；原文={raw!r}"))
                continue
        if any(m in raw for m in DSML_MARKERS):
            rows.append(("FAIL", f"{proto}:{name}", f"arguments 里残留 DSML 标记，解析未闭合；原文={raw[:160]!r}"))
            continue
        if not isinstance(parsed, dict):
            rows.append(("WARN", f"{proto}:{name}", f"arguments 解析为 {type(parsed).__name__}，非对象；值={parsed!r}"))
            continue
        rows.append(("PASS", f"{proto}:{name}", f"JSON 合法，{len(parsed)} 个参数：{sorted(parsed)}"))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--json", help="直接传入响应 JSON 字符串")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    docs: list[tuple[str, dict]] = []
    for f in a.files:
        with open(f, encoding="utf-8") as fh:
            docs.append((f, json.load(fh)))
    if a.json:
        docs.append(("<inline>", json.loads(a.json)))
    if not docs:
        print("no input: pass files or --json", file=sys.stderr)
        return 2

    bad = 0
    for src, doc in docs:
        rows = check(doc, src)
        fails = [r for r in rows if r[0] == "FAIL"]
        bad += len(fails)
        if not a.quiet:
            print(f"== {src}")
            for level, name, detail in rows:
                print(f"  [{level}] {name} :: {detail}")
    print(f"\nRESULT: {'FAIL' if bad else 'OK'} ({bad} 个不可用工具调用)")
    return 3 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
