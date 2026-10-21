#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hermes_ops_collect.py — 汇总 Hermes 的 token 消耗 + 任务/会话记录，产出 dsh 侧可见的运维快照。

只读数据源 (R/O URI, 绝不写 Hermes 库):
  D:\\hermes\\hermes-data\\profiles\\mybot\\state.db   (session_model_usage / sessions / messages)
  D:\\hermes\\hermes-data\\kanban.db                    (tasks / task_events)

产出:
  1) D:\\hermes\\hermes-data\\profiles\\mybot\\ops\\hermes_ops.json   机器可读快照
  2) C:\\Users\\Administrator\\Documents\\deepseek-harness\\default-workspace\\HERMES-OPS.md  人读看板
  3) MemOS (memos_vec.db) 一条 source='ops:hermes' 的自然语言摘要 (同 dsh_memos_ingest.py 的安全模式)

total_tokens 口径: input + output + cache_read + cache_write + reasoning (gross "touched tokens")。
  注意 cache_read 通常极大(缓存命中), 会主导该数字; 这不是计费 token。

CLI:
  python hermes_ops_collect.py                 # 默认 7 天
  python hermes_ops_collect.py --since-days 30
  python hermes_ops_collect.py --since 2026-10-01T00:00:00
  python hermes_ops_collect.py --all           # 不限时间
  python hermes_ops_collect.py --json          # stdout 只输出 JSON 快照
  python hermes_ops_collect.py --no-memos      # 跳过 MemOS 写入
  python hermes_ops_collect.py --dry-run       # 计算并打印, 不写任何文件/库
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------- paths

STATE_DB = Path(r"D:\hermes\hermes-data\profiles\mybot\state.db")
KANBAN_DB = Path(r"D:\hermes\hermes-data\kanban.db")
MEMOS_DB = Path(r"D:\hermes\hermes-data\profiles\mybot\knowledge_base\memos_vec.db")
OPS_DIR = Path(r"D:\hermes\hermes-data\profiles\mybot\ops")
OPS_JSON = OPS_DIR / "hermes_ops.json"
DASHBOARD = Path(r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\HERMES-OPS.md")

OPS_SOURCE = "ops:hermes"
TOP_SESSIONS_LIMIT = 20
SUMMARY_MIN, SUMMARY_MAX = 300, 800

TOKEN_COLS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens")


def ro_connect(path: Path) -> sqlite3.Connection:
    """Open a SQLite DB strictly read-only (URI mode=ro)."""
    uri = "file:" + str(path).replace("\\", "/") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts)).astimezone().isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return None


def day_of(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts)).astimezone().strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return None


def total_of(row: sqlite3.Row) -> int:
    return sum(int(row[c] or 0) for c in TOKEN_COLS)


# ----------------------------------------------------------- range parsing


def resolve_range(args) -> Tuple[Optional[float], Optional[int], str, str]:
    now = datetime.now().astimezone()
    now_ts = now.timestamp()
    if args.all:
        return None, None, None, iso(now_ts)  # type: ignore[return-value]
    if args.since:
        try:
            dt = datetime.fromisoformat(args.since)
        except ValueError:
            raise SystemExit(f"--since is not ISO8601: {args.since!r}")
        if dt.tzinfo is None:
            dt = dt.astimezone()
        return dt.timestamp(), None, iso(dt.timestamp()), iso(now_ts)  # type: ignore[return-value]
    days = args.since_days if args.since_days is not None else 7
    if days <= 0:
        raise SystemExit("--since-days must be > 0")
    since_ts = now_ts - days * 86400.0
    return since_ts, days, iso(since_ts), iso(now_ts)  # type: ignore[return-value]


# ------------------------------------------------------------- state.db


def collect_state(since: Optional[float]) -> Dict[str, Any]:
    """Aggregate the token-usage ledger (session_model_usage) + sessions metadata.

    Window is applied to `session_model_usage.last_seen`; `sessions` only enriches
    rows with source/model/title/message_count/tool_call_count. Orphan usage rows
    (session_id absent from `sessions`) are kept with source/model = "unknown".
    """
    con = ro_connect(STATE_DB)
    try:
        cur = con.cursor()
        meta: Dict[str, dict] = {}
        for r in cur.execute(
            "SELECT id, source, model, title, started_at, last_activity_at, ended_at, "
            "message_count, tool_call_count FROM sessions"
        ):
            meta[r["id"]] = {
                "source": r["source"] or "", "model": r["model"] or "", "title": r["title"] or "",
                "started_at": r["started_at"], "last_activity_at": r["last_activity_at"],
                "ended_at": r["ended_at"],
                "message_count": int(r["message_count"] or 0),
                "tool_call_count": int(r["tool_call_count"] or 0),
            }

        if since is None:
            where, params = "", ()
        else:
            where, params = "WHERE last_seen >= ?", (since,)
        usage_rows = cur.execute(
            "SELECT session_id, model, api_call_count, input_tokens, output_tokens, "
            "cache_read_tokens, cache_write_tokens, reasoning_tokens, "
            "estimated_cost_usd, actual_cost_usd, last_seen "
            f"FROM session_model_usage {where}", params
        ).fetchall()

        def blank():
            return {"api_calls": 0, "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
                    "cache_write_tokens": 0, "reasoning_tokens": 0, "estimated_cost_usd": 0.0,
                    "actual_cost_usd": 0.0}

        by_model_acc: Dict[str, dict] = {}
        by_model_sess: Dict[str, set] = defaultdict(set)
        by_day_acc: Dict[str, dict] = {}
        by_day_sess: Dict[str, set] = defaultdict(set)
        by_src_acc: Dict[str, dict] = {}
        by_src_sess: Dict[str, set] = defaultdict(set)
        sess_acc: Dict[str, dict] = {}
        seen_sessions: set = set()

        for r in usage_rows:
            sid = r["session_id"]
            seen_sessions.add(sid)
            m = r["model"] or "unknown"
            src = (meta.get(sid) or {}).get("source") or "unknown"
            d = day_of(r["last_seen"]) or "unknown"
            row = {
                "api_calls": int(r["api_call_count"] or 0),
                "input_tokens": int(r["input_tokens"] or 0),
                "output_tokens": int(r["output_tokens"] or 0),
                "cache_read_tokens": int(r["cache_read_tokens"] or 0),
                "cache_write_tokens": int(r["cache_write_tokens"] or 0),
                "reasoning_tokens": int(r["reasoning_tokens"] or 0),
                "estimated_cost_usd": float(r["estimated_cost_usd"] or 0.0),
                "actual_cost_usd": float(r["actual_cost_usd"] or 0.0),
            }
            for acc, key in ((by_model_acc, m), (by_day_acc, d), (by_src_acc, src), (sess_acc, sid)):
                a = acc.setdefault(key, blank())
                for c in ("api_calls", *TOKEN_COLS):
                    a[c] += row[c]
                a["estimated_cost_usd"] += row["estimated_cost_usd"]
                a["actual_cost_usd"] += row["actual_cost_usd"]
            by_model_sess[m].add(sid)
            by_day_sess[d].add(sid)
            by_src_sess[src].add(sid)

        def tok(a: dict) -> int:
            return sum(int(a[c]) for c in TOKEN_COLS)

        by_model = [{
            "model": m, "api_calls": a["api_calls"], "input_tokens": a["input_tokens"],
            "output_tokens": a["output_tokens"], "cache_read_tokens": a["cache_read_tokens"],
            "reasoning_tokens": a["reasoning_tokens"],
            "estimated_cost_usd": round(a["estimated_cost_usd"], 6),
            "sessions": len(by_model_sess[m]),
        } for m, a in by_model_acc.items()]
        by_model.sort(key=lambda x: x["input_tokens"] + x["output_tokens"] + x["cache_read_tokens"] + x["reasoning_tokens"], reverse=True)

        by_day = [{
            "day": d, "sessions": len(by_day_sess[d]), "api_calls": a["api_calls"],
            "total_tokens": tok(a), "estimated_cost_usd": round(a["estimated_cost_usd"], 6),
        } for d, a in by_day_acc.items()]
        by_day.sort(key=lambda x: x["day"])

        by_source = [{"source": s, "sessions": len(by_src_sess[s]), "total_tokens": tok(a)}
                     for s, a in by_src_acc.items()]
        by_source.sort(key=lambda x: x["total_tokens"], reverse=True)

        top: List[dict] = []
        for sid, a in sess_acc.items():
            mi = meta.get(sid) or {}
            top.append({
                "session_id": sid,
                "title": mi.get("title", ""),
                "source": mi.get("source") or "unknown",
                "model": mi.get("model") or "",
                "started_at": iso(mi.get("started_at")),
                "last_activity_at": iso(mi.get("last_activity_at")),
                "message_count": mi.get("message_count", 0),
                "tool_call_count": mi.get("tool_call_count", 0),
                "total_tokens": tok(a),
                "estimated_cost_usd": round(a["estimated_cost_usd"], 6),
            })
        top.sort(key=lambda x: x["total_tokens"], reverse=True)
        top = top[:TOP_SESSIONS_LIMIT]

        totals = blank()
        for a in sess_acc.values():
            for c in ("api_calls", *TOKEN_COLS):
                totals[c] += a[c]
            totals["estimated_cost_usd"] += a["estimated_cost_usd"]
            totals["actual_cost_usd"] += a["actual_cost_usd"]
        totals["sessions"] = len(seen_sessions)
        totals["estimated_cost_usd"] = round(totals["estimated_cost_usd"], 6)
        totals["actual_cost_usd"] = round(totals["actual_cost_usd"], 6)
        totals["total_tokens"] = tok(totals)
        if since is None:
            totals["messages"] = cur.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        else:
            totals["messages"] = cur.execute("SELECT COUNT(*) FROM messages WHERE timestamp >= ?", (since,)).fetchone()[0]

        return {"totals": totals, "by_model": by_model, "by_day": by_day,
                "by_source": by_source, "top_sessions": top}
    finally:
        con.close()


# --------------------------------------------------------------- kanban


def collect_tasks() -> Dict[str, Any]:
    con = ro_connect(KANBAN_DB)
    try:
        cur = con.cursor()
        items: List[dict] = []
        by_status: Dict[str, int] = {}
        for r in cur.execute(
            "SELECT id, title, assignee, status, priority, created_at, started_at, completed_at, "
            "reasoning_effort, session_id, result FROM tasks ORDER BY created_at"
        ):
            by_status[r["status"] or "unknown"] = by_status.get(r["status"] or "unknown", 0) + 1
            items.append({
                "id": r["id"], "title": r["title"] or "", "status": r["status"] or "",
                "assignee": r["assignee"] or "", "priority": r["priority"],
                "created_at": iso(r["created_at"]), "started_at": iso(r["started_at"]),
                "completed_at": iso(r["completed_at"]),
                "reasoning_effort": r["reasoning_effort"], "session_id": r["session_id"],
                "result": (r["result"] or "")[:500],
            })
        events = []
        for r in cur.execute("SELECT task_id, kind, created_at FROM task_events ORDER BY created_at, id"):
            events.append({"task_id": r["task_id"], "kind": r["kind"], "created_at": iso(r["created_at"])})
        return {"tasks": {"total": len(items), "by_status": by_status, "items": items},
                "task_events": events}
    finally:
        con.close()


# ------------------------------------------------------------- rendering


def fmt_int(n: int) -> str:
    return f"{int(n):,}"


def render_markdown(snap: dict) -> str:
    t = snap["totals"]; rng = snap["range"]
    L: List[str] = []
    L.append("# Hermes 运营看板 (HERMES-OPS)")
    L.append("")
    L.append(f"> 生成时间：{snap['generated_at']}　|　区间："
             f"{rng['since_days'] if rng['since_days'] is not None else 'ALL'} 天　"
             f"({rng['from'] or '起始'} → {rng['to']})")
    L.append(">")
    L.append("> `total_tokens` = input + output + cache_read + cache_write + reasoning（gross，含缓存命中；"
             "`cache_read` 通常远大于其余项）。金额单位 USD。")
    L.append("")
    L.append("## 总体")
    L.append("")
    L.append("| 指标 | 值 | 指标 | 值 |")
    L.append("|---|---:|---|---:|")
    L.append(f"| 会话数 | {fmt_int(t['sessions'])} | 消息数 | {fmt_int(t['messages'])} |")
    L.append(f"| API 调用 | {fmt_int(t['api_calls'])} | 总 token(gross) | {fmt_int(t['total_tokens'])} |")
    L.append(f"| input | {fmt_int(t['input_tokens'])} | output | {fmt_int(t['output_tokens'])} |")
    L.append(f"| cache_read | {fmt_int(t['cache_read_tokens'])} | cache_write | {fmt_int(t['cache_write_tokens'])} |")
    L.append(f"| reasoning | {fmt_int(t['reasoning_tokens'])} | 预估成本 | ${t['estimated_cost_usd']:.4f} |")
    L.append(f"| 实际成本 | ${t['actual_cost_usd']:.4f} | | |")
    L.append("")
    L.append("## 按模型")
    L.append("")
    L.append("| 模型 | 会话 | API 调用 | input | output | cache_read | reasoning | 总 token | 预估成本 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for m in snap["by_model"]:
        tt = m["input_tokens"] + m["output_tokens"] + m["cache_read_tokens"] + m["reasoning_tokens"]
        L.append(f"| `{m['model']}` | {fmt_int(m['sessions'])} | {fmt_int(m['api_calls'])} | "
                 f"{fmt_int(m['input_tokens'])} | {fmt_int(m['output_tokens'])} | {fmt_int(m['cache_read_tokens'])} | "
                 f"{fmt_int(m['reasoning_tokens'])} | {fmt_int(tt)} | ${m['estimated_cost_usd']:.4f} |")
    L.append("")
    L.append("## 按天趋势")
    L.append("")
    L.append("| 日期 | 会话 | API 调用 | 总 token | 预估成本 |")
    L.append("|---|---:|---:|---:|---:|")
    for d in snap["by_day"]:
        L.append(f"| {d['day']} | {fmt_int(d['sessions'])} | {fmt_int(d['api_calls'])} | "
                 f"{fmt_int(d['total_tokens'])} | ${d['estimated_cost_usd']:.4f} |")
    L.append("")
    L.append("## 按来源")
    L.append("")
    L.append("| 来源 | 会话 | 总 token |")
    L.append("|---|---:|---:|")
    for s in snap["by_source"]:
        L.append(f"| `{s['source']}` | {fmt_int(s['sessions'])} | {fmt_int(s['total_tokens'])} |")
    L.append("")
    L.append(f"## Top {len(snap['top_sessions'])} 会话（按总 token）")
    L.append("")
    L.append("| session_id | 标题 | 来源 | 模型 | 消息 | 工具调用 | 总 token | 预估成本 | 最后活动 |")
    L.append("|---|---|---|---|---:|---:|---:|---:|---|")
    for s in snap["top_sessions"]:
        title = (s["title"] or "").replace("|", "/")[:40]
        L.append(f"| `{s['session_id']}` | {title} | `{s['source']}` | `{s['model']}` | "
                 f"{fmt_int(s['message_count'])} | {fmt_int(s['tool_call_count'])} | "
                 f"{fmt_int(s['total_tokens'])} | ${s['estimated_cost_usd']:.4f} | {s['last_activity_at']} |")
    L.append("")
    tk = snap["tasks"]
    L.append("## 任务看板")
    L.append("")
    L.append(f"共 {tk['total']} 条；状态分布：" + "、".join(f"{k}={v}" for k, v in sorted(tk["by_status"].items())))
    L.append("")
    L.append("| id | 标题 | 状态 | 负责人 | 优先级 | 创建 | 完成 | reasoning_effort | session |")
    L.append("|---|---|---|---|---:|---|---|---|---|")
    for x in tk["items"]:
        title = (x["title"] or "").replace("|", "/")[:60]
        L.append(f"| `{x['id']}` | {title} | **{x['status']}** | {x['assignee']} | {x['priority']} | "
                 f"{x['created_at']} | {x['completed_at'] or '-'} | {x['reasoning_effort'] or '-'} | {x['session_id'] or '-'} |")
    L.append("")
    L.append(f"（task_events 共 {len(snap['task_events'])} 条，详见 `ops/hermes_ops.json`。）")
    L.append("")
    return "\n".join(L)


def build_summary_text(snap: dict) -> str:
    t = snap["totals"]; rng = snap["range"]
    days = rng["since_days"]
    win = f"近 {days} 天" if days is not None else "全量"
    top_models = "、".join(f"{m['model']}({fmt_int(m['input_tokens'] + m['output_tokens'] + m['cache_read_tokens'] + m['reasoning_tokens'])})"
                           for m in snap["by_model"][:3])
    days_sorted = snap["by_day"]
    if days_sorted:
        first, last = days_sorted[0], days_sorted[-1]
        trend = (f"区间内共 {len(days_sorted)} 个活跃日，从 {first['day']} 到 {last['day']}；"
                 f"单日总 token 最高的是 " + max(days_sorted, key=lambda d: d["total_tokens"])["day"] +
                 f"（{fmt_int(max(days_sorted, key=lambda d: d['total_tokens'])['total_tokens'])}）")
    else:
        trend = "区间内无活跃日"
    tk = snap["tasks"]
    status_txt = "、".join(f"{k} {v} 条" for k, v in sorted(tk["by_status"].items())) or "无任务"
    blocked = [x for x in tk["items"] if x["status"] == "blocked"]
    blocked_txt = f"其中长期 blocked {len(blocked)} 条" if blocked else ""
    text = (
        f"Hermes 运营汇总（{win}，{rng['from'] or '起始'} → {rng['to']}）："
        f"共 {fmt_int(t['sessions'])} 个会话、{fmt_int(t['messages'])} 条消息、{fmt_int(t['api_calls'])} 次 API 调用。"
        f"token 总量(gross) {fmt_int(t['total_tokens'])}，其中 input {fmt_int(t['input_tokens'])}、"
        f"output {fmt_int(t['output_tokens'])}、cache_read {fmt_int(t['cache_read_tokens'])}、"
        f"reasoning {fmt_int(t['reasoning_tokens'])}；预估成本 ${t['estimated_cost_usd']:.4f}（实际成本 ${t['actual_cost_usd']:.4f}）。"
        f"按模型看，{top_models}。"
        f"{trend}。"
        f"任务看板共 {tk['total']} 条，状态分布：{status_txt}{blocked_txt}。"
        "注意：total_tokens 含大幅缓存命中(cache_read)，不等于计费 token；成本字段部分为 0/unknown。"
    )
    if len(text) > SUMMARY_MAX:
        text = text[:SUMMARY_MAX - 3] + "..."
    return text


# ------------------------------------------------------------- MemOS write


def count_sources(con: sqlite3.Connection) -> Dict[str, int]:
    return {r[0]: r[1] for r in con.execute("SELECT source, COUNT(*) FROM memos_body GROUP BY source")}


def write_memos(snap: dict, summary: str, dry_run: bool) -> dict:
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    session_id = f"{OPS_SOURCE}:{today}"
    title = f"Hermes 运营汇总 {today}"
    now_ts = datetime.now().astimezone().timestamp()
    result = {"session_id": session_id, "session_title": title, "content_chars": len(summary),
              "written": False, "hermes_before": None, "hermes_after": None, "invariant_ok": None}
    if dry_run:
        result["summary_preview"] = summary[:200]
        return result
    con = sqlite3.connect(str(MEMOS_DB), timeout=60)
    con.execute("PRAGMA busy_timeout=60000")
    try:
        with con:
            before = count_sources(con)
            hermes_before = sum(v for k, v in before.items() if k.startswith("hermes:"))
            dsh_before = sum(v for k, v in before.items() if k.startswith("dsh:"))
            # only ever touch ops:hermes rows
            con.execute("DELETE FROM memos_body WHERE source LIKE 'ops:hermes%' AND session_id = ?", (session_id,))
            con.execute(
                "INSERT INTO memos_body(session_id, message_id, role, content, session_title, source, created_at, token_count)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, 1, "system", summary, title, OPS_SOURCE, now_ts, max(1, len(summary) // 4)),
            )
            after = count_sources(con)
            hermes_after = sum(v for k, v in after.items() if k.startswith("hermes:"))
            dsh_after = sum(v for k, v in after.items() if k.startswith("dsh:"))
            if hermes_after != hermes_before or dsh_after != dsh_before:
                raise RuntimeError(
                    f"INVARIANT VIOLATED: hermes {hermes_before}->{hermes_after}, dsh {dsh_before}->{dsh_after}")
            con.execute("INSERT INTO memos_fts(memos_fts) VALUES('rebuild')")
            result.update({"written": True, "hermes_before": hermes_before, "hermes_after": hermes_after,
                           "dsh_before": dsh_before, "dsh_after": dsh_after, "invariant_ok": True})
    finally:
        con.close()
    return result


# ------------------------------------------------------------------ main


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Collect Hermes ops snapshot (tokens + tasks) for dsh")
    ap.add_argument("--since-days", type=int, default=None, help="window in days (default 7)")
    ap.add_argument("--since", default=None, help="ISO8601 lower bound (overrides --since-days)")
    ap.add_argument("--all", action="store_true", help="no time bound")
    ap.add_argument("--json", action="store_true", help="stdout is the JSON snapshot only")
    ap.add_argument("--no-memos", action="store_true", help="skip the MemOS summary write")
    ap.add_argument("--dry-run", action="store_true", help="compute and print, write nothing")
    ap.add_argument("--state-db", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--kanban-db", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    global STATE_DB, KANBAN_DB
    if args.state_db:
        STATE_DB = Path(args.state_db)
    if args.kanban_db:
        KANBAN_DB = Path(args.kanban_db)

    since, since_days, from_iso, to_iso = resolve_range(args)
    state = collect_state(since)
    kanban = collect_tasks()
    snap = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "range": {"since_days": since_days, "from": from_iso, "to": to_iso},
        "totals": state["totals"],
        "by_model": state["by_model"],
        "by_day": state["by_day"],
        "by_source": state["by_source"],
        "top_sessions": state["top_sessions"],
        "tasks": kanban["tasks"],
        "task_events": kanban["task_events"],
    }
    summary = build_summary_text(snap)

    memos_result = {"written": False, "skipped": True} if args.no_memos else write_memos(snap, summary, args.dry_run)
    snap["memos"] = memos_result

    if not args.dry_run:
        OPS_DIR.mkdir(parents=True, exist_ok=True)
        OPS_JSON.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
        DASHBOARD.write_text(render_markdown(snap), encoding="utf-8")

    if args.json:
        print(json.dumps(snap, ensure_ascii=False, indent=2))
    else:
        t = snap["totals"]
        print(f"range: {from_iso or 'ALL'} -> {to_iso}")
        print(f"sessions={t['sessions']} messages={t['messages']} api_calls={t['api_calls']}")
        print(f"tokens: input={t['input_tokens']} output={t['output_tokens']} cache_read={t['cache_read_tokens']} "
              f"reasoning={t['reasoning_tokens']} total={t['total_tokens']}")
        print(f"cost: estimated=${t['estimated_cost_usd']:.6f} actual=${t['actual_cost_usd']:.6f}")
        print(f"by_model: " + "; ".join(f"{m['model']} sessions={m['sessions']} in={m['input_tokens']} out={m['output_tokens']}" for m in snap["by_model"]))
        print(f"tasks: total={snap['tasks']['total']} by_status={json.dumps(snap['tasks']['by_status'], ensure_ascii=False)}")
        print(f"memos: {json.dumps(memos_result, ensure_ascii=False)}")
        if not args.dry_run:
            print(f"wrote: {OPS_JSON}")
            print(f"wrote: {DASHBOARD}")
        else:
            print("[dry-run] no files / no memos written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())