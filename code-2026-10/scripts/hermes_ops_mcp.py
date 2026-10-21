#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hermes_ops_mcp.py -- single-file stdio MCP server exposing Hermes token usage
and task/session records to an external agent (dsh).

Data sources (STRICTLY READ-ONLY: sqlite URI mode=ro + PRAGMA query_only=ON,
SELECT statements only; this process can never write to either database):

  * <profile>/state.db          table session_model_usage  (token usage rows)
                                table sessions              (session records)
  * <hermes-data>/kanban.db     table tasks                 (kanban tasks)
                                table task_events           (task event log)

Transport: MCP 2024-11-05 over stdio, newline-delimited JSON-RPC 2.0.
stdout carries ONLY one JSON-RPC frame per line; all logging goes to stderr.

Timestamps: every time column on this install is Unix epoch SECONDS
(REAL with sub-second precision in state.db, INTEGER in kanban.db).
The unit is detected per (table, column) on first use and normalized to
epoch seconds; ISO output is rendered in UTC+08:00 (Asia/Shanghai).

Launch (pure argv, no shell):
  "C:\\Users\\Administrator\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\python.exe"
  -u "D:\\hermes\\hermes-data\\profiles\\mybot\\scripts\\hermes_ops_mcp.py"

Optional env overrides: HERMES_OPS_STATE_DB, HERMES_OPS_KANBAN_DB.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "hermes-ops"
SERVER_VERSION = "1.0.0"

TZ8 = timezone(timedelta(hours=8))
MAX_LIMIT = 200
MAX_SINCE_DAYS = 3650
DEFAULT_SINCE_DAYS = 7
DEFAULT_SESSION_LIMIT = 20
DEFAULT_TASK_LIMIT = 50
GROUP_BY_CHOICES = ("model", "day", "source", "session", "none")
UNIT_MULT = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9}
UNIT_THRESHOLDS = ((1e17, "ns"), (1e14, "us"), (1e11, "ms"))

SCRIPT_DIR = Path(__file__).resolve().parent
PROFILE_HOME = SCRIPT_DIR.parent
HERMES_DATA = SCRIPT_DIR.parents[2]


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw) if raw else default


STATE_DB = _env_path("HERMES_OPS_STATE_DB", PROFILE_HOME / "state.db")
KANBAN_DB = _env_path("HERMES_OPS_KANBAN_DB", HERMES_DATA / "kanban.db")

log = logging.getLogger("hermes-ops")
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("[hermes-ops] %(levelname)s %(message)s"))
    log.addHandler(_h)
log.setLevel(logging.INFO)
log.propagate = False


class ToolError(Exception):
    """Raised by a tool implementation; rendered as an MCP isError result."""

    def __init__(self, message: str, code: str = "ops_error") -> None:
        super().__init__(message)
        self.code = code


def _readonly_connect(path: Path) -> sqlite3.Connection:
    """Open a DB strictly read-only. Prefer the SQLite URI mode=ro; if the URI
    form is unavailable for any reason, fall back to a normal handle immediately
    pinned with PRAGMA query_only=ON so no statement can write."""
    if not path.exists():
        raise ToolError("database not found: %s" % path, "db_unavailable")
    uri = path.as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=15)
    except sqlite3.Error as exc:
        log.warning("read-only URI open failed (%s); falling back to query_only", exc)
        conn = sqlite3.connect(str(path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn

# ---------------------------------------------------------------------------
# Timestamp unit detection + normalization
# ---------------------------------------------------------------------------

_TS_UNIT_CACHE: dict[tuple, dict] = {}


def _classify_magnitude(value: Any) -> str:
    try:
        magnitude = abs(float(value))
    except (TypeError, ValueError):
        return "s"
    for threshold, unit in UNIT_THRESHOLDS:
        if magnitude >= threshold:
            return unit
    return "s"


def _detect_ts_unit(conn: sqlite3.Connection, db_key: str, table: str, col: str) -> dict:
    """Probe up to 64 non-null values of a time column and classify the unit.

    Cached per (db_key, table, col). Returns a dict with unit/samples/min/max so
    ops_health can show the raw evidence."""
    key = (db_key, table, col)
    cached = _TS_UNIT_CACHE.get(key)
    if cached is not None:
        return cached
    vals: list[float] = []
    try:
        rows = conn.execute(
            'SELECT "%s" FROM "%s" WHERE "%s" IS NOT NULL LIMIT 64' % (col, table, col)
        ).fetchall()
        for row in rows:
            raw = row[0]
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                continue
            vals.append(float(raw))
    except sqlite3.Error as exc:
        info = {"unit": "s", "detected": False, "samples": 0, "error": str(exc)}
        _TS_UNIT_CACHE[key] = info
        return info
    units = sorted({_classify_magnitude(v) for v in vals})
    if not units:
        unit = "s"
    elif len(units) == 1:
        unit = units[0]
    else:
        unit = "mixed:" + ",".join(units)
    info = {
        "unit": unit,
        "detected": bool(vals),
        "samples": len(vals),
        "min": min(vals) if vals else None,
        "max": max(vals) if vals else None,
    }
    _TS_UNIT_CACHE[key] = info
    return info


def _unit_mult(conn: sqlite3.Connection, db_key: str, table: str, col: str) -> float:
    """Multiplier that converts this column's raw value into epoch SECONDS."""
    unit = _detect_ts_unit(conn, db_key, table, col).get("unit", "s")
    return UNIT_MULT.get(unit, 1.0)


def _to_epoch_seconds(value: Any, mult: float) -> float | None:
    if value is None:
        return None
    try:
        return float(value) * mult
    except (TypeError, ValueError):
        return None


def _iso(epoch_seconds: Any, timespec: str = "seconds") -> str | None:
    if epoch_seconds is None:
        return None
    try:
        return datetime.fromtimestamp(float(epoch_seconds), tz=TZ8).isoformat(timespec=timespec)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _iso_col(value: Any, mult: float) -> str | None:
    return _iso(_to_epoch_seconds(value, mult))


def _day_label(day_idx: Any) -> str:
    try:
        return datetime.fromtimestamp(int(day_idx) * 86400, tz=TZ8).date().isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return str(day_idx)


def _cutoff_epoch(since_days: int) -> float:
    return time.time() - since_days * 86400.0


def _cutoff_in_unit(since_days: int, mult: float) -> float:
    cut = _cutoff_epoch(since_days)
    return cut / mult if mult else cut


def _int0(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float0(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _snippet(value: Any, limit: int = 400) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[:limit] if len(text) > limit else text


# ---------------------------------------------------------------------------
# Argument validation (lenient but bounded)
# ---------------------------------------------------------------------------

def _int_arg(args: dict, key: str, default: int, low: int, high: int) -> int:
    value = args.get(key, default)
    if value is None:
        value = default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolError("%s must be an integer" % key, "bad_argument")
    ivalue = int(value)
    if ivalue < low or ivalue > high:
        raise ToolError("%s must be between %d and %d" % (key, low, high), "bad_argument")
    return ivalue


def _opt_int_arg(args: dict, key: str, low: int, high: int) -> int | None:
    value = args.get(key)
    if value is None or value == "":
        return None
    return _int_arg(args, key, None, low, high)  # type: ignore[arg-type]


def _opt_str_arg(args: dict, key: str) -> str | None:
    value = args.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None

# ---------------------------------------------------------------------------
# Shared SQL fragments
# ---------------------------------------------------------------------------

_USAGE_METRIC_SQL = (
    "COUNT(*) AS usage_rows, "
    "COUNT(DISTINCT smu.session_id) AS sessions, "
    "COALESCE(SUM(smu.api_call_count), 0) AS api_calls, "
    "COALESCE(SUM(smu.input_tokens), 0) AS input_tokens, "
    "COALESCE(SUM(smu.output_tokens), 0) AS output_tokens, "
    "COALESCE(SUM(smu.cache_read_tokens), 0) AS cache_read_tokens, "
    "COALESCE(SUM(smu.cache_write_tokens), 0) AS cache_write_tokens, "
    "COALESCE(SUM(smu.reasoning_tokens), 0) AS reasoning_tokens, "
    "COALESCE(SUM(smu.input_tokens), 0) + COALESCE(SUM(smu.output_tokens), 0) AS total_tokens, "
    "COALESCE(SUM(smu.estimated_cost_usd), 0) AS estimated_cost_usd, "
    "COALESCE(SUM(smu.actual_cost_usd), 0) AS actual_cost_usd"
)

TOTAL_TOKENS_DEFINITION = (
    "input_tokens + output_tokens. Cache tokens (cache_read_tokens, cache_write_tokens) "
    "and reasoning_tokens are reported separately and are NOT included in total_tokens."
)


def _usage_metrics(row: sqlite3.Row) -> dict:
    return {
        "usage_rows": _int0(row["usage_rows"]),
        "sessions": _int0(row["sessions"]),
        "api_calls": _int0(row["api_calls"]),
        "input_tokens": _int0(row["input_tokens"]),
        "output_tokens": _int0(row["output_tokens"]),
        "cache_read_tokens": _int0(row["cache_read_tokens"]),
        "cache_write_tokens": _int0(row["cache_write_tokens"]),
        "reasoning_tokens": _int0(row["reasoning_tokens"]),
        "total_tokens": _int0(row["total_tokens"]),
        "estimated_cost_usd": round(_float0(row["estimated_cost_usd"]), 6),
        "actual_cost_usd": round(_float0(row["actual_cost_usd"]), 6),
    }


def _open_state() -> sqlite3.Connection:
    try:
        return _readonly_connect(STATE_DB)
    except ToolError:
        raise
    except sqlite3.Error as exc:
        raise ToolError("cannot open state.db read-only: %s" % exc, "db_unavailable") from exc


def _open_kanban() -> sqlite3.Connection:
    try:
        return _readonly_connect(KANBAN_DB)
    except ToolError:
        raise
    except sqlite3.Error as exc:
        raise ToolError("cannot open kanban.db read-only: %s" % exc, "db_unavailable") from exc


# ---------------------------------------------------------------------------
# Tool 1: usage_summary
# ---------------------------------------------------------------------------

def _t_usage_summary(args: dict) -> dict:
    since_days = _int_arg(args, "since_days", DEFAULT_SINCE_DAYS, 0, MAX_SINCE_DAYS)
    group_by = str(args.get("group_by") or "model").strip().lower()
    if group_by not in GROUP_BY_CHOICES:
        raise ToolError("group_by must be one of %s" % (", ".join(GROUP_BY_CHOICES)), "bad_argument")

    conn = _open_state()
    try:
        ts_last = _detect_ts_unit(conn, "state", "session_model_usage", "last_seen")
        ts_first = _detect_ts_unit(conn, "state", "session_model_usage", "first_seen")
        mult = _unit_mult(conn, "state", "session_model_usage", "last_seen")
        cutoff = _cutoff_in_unit(since_days, mult)

        where = "WHERE COALESCE(smu.last_seen, smu.first_seen) >= ?"
        join = ""
        group_expr = None
        extra_select = ""
        if group_by == "model":
            group_expr = "COALESCE(NULLIF(smu.model, ''), '(unknown)')"
        elif group_by == "day":
            group_expr = ("CAST((COALESCE(smu.last_seen, smu.first_seen) * %s + 28800) "
                          "/ 86400 AS INTEGER)" % repr(mult))
        elif group_by == "source":
            join = "LEFT JOIN sessions s ON s.id = smu.session_id"
            group_expr = "COALESCE(NULLIF(s.source, ''), '(unknown)')"
        elif group_by == "session":
            join = "LEFT JOIN sessions s ON s.id = smu.session_id"
            group_expr = "smu.session_id"
            extra_select = ", s.title AS title, s.source AS source, s.model AS session_model"

        total_sql = "SELECT " + _USAGE_METRIC_SQL + " FROM session_model_usage smu " + join + " " + where
        total_row = conn.execute(total_sql, (cutoff,)).fetchone()

        groups: list[dict] = []
        if group_expr is not None:
            order_sql = "grp DESC" if group_by == "day" else "total_tokens DESC"
            group_sql = (
                "SELECT " + group_expr + " AS grp" + extra_select + ", " + _USAGE_METRIC_SQL +
                " FROM session_model_usage smu " + join + " " + where +
                " GROUP BY grp ORDER BY " + order_sql + " LIMIT ?"
            )
            for row in conn.execute(group_sql, (cutoff, MAX_LIMIT)):
                key = row["grp"]
                item = {"key": _day_label(key) if group_by == "day" else (key if key is not None else "(unknown)")}
                if group_by == "session":
                    item["title"] = row["title"]
                    item["source"] = row["source"]
                    item["model"] = row["session_model"]
                elif group_by == "day":
                    item["day"] = item["key"]
                item.update(_usage_metrics(row))
                groups.append(item)

        return {
            "ok": True,
            "source": str(STATE_DB),
            "table": "session_model_usage",
            "since_days": since_days,
            "since": _iso(_cutoff_epoch(since_days)),
            "until": _iso(time.time()),
            "group_by": group_by,
            "window_column": "COALESCE(session_model_usage.last_seen, session_model_usage.first_seen)",
            "timestamp_unit": {"last_seen": ts_last.get("unit"), "first_seen": ts_first.get("unit")},
            "total_tokens_definition": TOTAL_TOKENS_DEFINITION,
            "totals": _usage_metrics(total_row),
            "groups": groups,
            "group_count": len(groups),
            "group_limit": MAX_LIMIT,
            "note": ("group_by=none: see totals." if group_by == "none"
                     else ("Groups ordered by day DESC." if group_by == "day"
                           else "Groups ordered by total_tokens DESC (max %d)." % MAX_LIMIT)),
        }
    except sqlite3.Error as exc:
        raise ToolError("state.db query failed: %s" % exc, "db_error") from exc
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Tool 2: sessions_list
# ---------------------------------------------------------------------------

def _t_sessions_list(args: dict) -> dict:
    since_days = _int_arg(args, "since_days", DEFAULT_SINCE_DAYS, 0, MAX_SINCE_DAYS)
    limit = _int_arg(args, "limit", DEFAULT_SESSION_LIMIT, 1, MAX_LIMIT)
    source = _opt_str_arg(args, "source")
    model = _opt_str_arg(args, "model")
    min_tokens = _opt_int_arg(args, "min_tokens", 0, 10 ** 15)

    conn = _open_state()
    try:
        mult = _unit_mult(conn, "state", "sessions", "last_activity_at")
        ts_started = _detect_ts_unit(conn, "state", "sessions", "started_at")
        ts_activity = _detect_ts_unit(conn, "state", "sessions", "last_activity_at")
        cutoff = _cutoff_in_unit(since_days, mult)

        total_expr = "(COALESCE(s.input_tokens, 0) + COALESCE(s.output_tokens, 0))"
        clauses = ["COALESCE(s.last_activity_at, s.started_at) >= ?"]
        params: list[Any] = [cutoff]
        if source:
            clauses.append("(s.source = ? OR s.source LIKE ? || '%')")
            params.extend([source, source])
        if model:
            clauses.append("s.model LIKE '%' || ? || '%'")
            params.append(model)
        if min_tokens is not None:
            clauses.append(total_expr + " >= ?")
            params.append(min_tokens)
        where = "WHERE " + " AND ".join(clauses)

        sql = (
            "SELECT s.id AS session_id, "
            "COALESCE(NULLIF(s.title, ''), s.display_name) AS title, "
            "s.source AS source, s.model AS model, "
            "s.started_at AS started_at, s.last_activity_at AS last_activity_at, "
            "s.ended_at AS ended_at, s.end_reason AS end_reason, "
            "COALESCE(s.message_count, 0) AS message_count, "
            "COALESCE(s.tool_call_count, 0) AS tool_call_count, "
            "COALESCE(s.input_tokens, 0) AS input_tokens, "
            "COALESCE(s.output_tokens, 0) AS output_tokens, "
            "COALESCE(s.cache_read_tokens, 0) AS cache_read_tokens, "
            "COALESCE(s.cache_write_tokens, 0) AS cache_write_tokens, "
            "COALESCE(s.reasoning_tokens, 0) AS reasoning_tokens, "
            + total_expr + " AS total_tokens, "
            "COALESCE(s.estimated_cost_usd, 0) AS estimated_cost_usd, "
            "COALESCE(s.actual_cost_usd, 0) AS actual_cost_usd, "
            "COALESCE(s.api_call_count, 0) AS api_calls, "
            "COALESCE(s.archived, 0) AS archived, COALESCE(s.pinned, 0) AS pinned "
            "FROM sessions s " + where +
            " ORDER BY total_tokens DESC, s.last_activity_at DESC LIMIT ?"
        )
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()

        items = []
        for r in rows:
            items.append({
                "session_id": r["session_id"],
                "title": r["title"],
                "source": r["source"],
                "model": r["model"],
                "started_at": _iso_col(r["started_at"], mult),
                "last_activity_at": _iso_col(r["last_activity_at"], mult),
                "ended_at": _iso_col(r["ended_at"], mult),
                "end_reason": r["end_reason"],
                "message_count": _int0(r["message_count"]),
                "tool_call_count": _int0(r["tool_call_count"]),
                "input_tokens": _int0(r["input_tokens"]),
                "output_tokens": _int0(r["output_tokens"]),
                "cache_read_tokens": _int0(r["cache_read_tokens"]),
                "cache_write_tokens": _int0(r["cache_write_tokens"]),
                "reasoning_tokens": _int0(r["reasoning_tokens"]),
                "total_tokens": _int0(r["total_tokens"]),
                "estimated_cost_usd": round(_float0(r["estimated_cost_usd"]), 6),
                "actual_cost_usd": round(_float0(r["actual_cost_usd"]), 6),
                "api_calls": _int0(r["api_calls"]),
                "archived": bool(_int0(r["archived"])),
                "pinned": bool(_int0(r["pinned"])),
            })

        return {
            "ok": True,
            "source": str(STATE_DB),
            "table": "sessions",
            "since_days": since_days,
            "since": _iso(_cutoff_epoch(since_days)),
            "until": _iso(time.time()),
            "window_column": "COALESCE(sessions.last_activity_at, sessions.started_at)",
            "timestamp_unit": {"started_at": ts_started.get("unit"),
                               "last_activity_at": ts_activity.get("unit")},
            "filters": {"source": source, "model": model, "min_tokens": min_tokens},
            "total_tokens_definition": TOTAL_TOKENS_DEFINITION,
            "count": len(items),
            "limit": limit,
            "items": items,
        }
    except sqlite3.Error as exc:
        raise ToolError("state.db query failed: %s" % exc, "db_error") from exc
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Tool 3: tasks_list
# ---------------------------------------------------------------------------

def _t_tasks_list(args: dict) -> dict:
    status = _opt_str_arg(args, "status")
    limit = _int_arg(args, "limit", DEFAULT_TASK_LIMIT, 1, MAX_LIMIT)

    conn = _open_kanban()
    try:
        mult = _unit_mult(conn, "kanban", "tasks", "created_at")
        _detect_ts_unit(conn, "kanban", "tasks", "started_at")
        _detect_ts_unit(conn, "kanban", "tasks", "completed_at")
        ev_mult = _unit_mult(conn, "kanban", "task_events", "created_at")

        by_status = {}
        for row in conn.execute(
            "SELECT status, COUNT(*) AS n FROM tasks GROUP BY status ORDER BY n DESC, status"
        ):
            by_status[row["status"]] = _int0(row["n"])

        clauses = []
        params: list[Any] = []
        if status:
            clauses.append("t.status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        sql = (
            "SELECT t.id, t.title, t.status, t.assignee, t.priority, "
            "t.created_at, t.started_at, t.completed_at, t.reasoning_effort, "
            "t.session_id, t.result, t.model_override, t.provider_override, "
            "t.workspace_path, t.project_id, t.consecutive_failures, t.body "
            "FROM tasks t " + where + " ORDER BY t.created_at DESC LIMIT ?"
        )
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()

        items = []
        for r in rows:
            items.append({
                "id": r["id"],
                "title": r["title"],
                "status": r["status"],
                "assignee": r["assignee"],
                "priority": _int0(r["priority"]),
                "created_at": _iso_col(r["created_at"], mult),
                "started_at": _iso_col(r["started_at"], mult),
                "completed_at": _iso_col(r["completed_at"], mult),
                "reasoning_effort": r["reasoning_effort"],
                "session_id": r["session_id"],
                "result": _snippet(r["result"], 600),
                "model_override": r["model_override"],
                "provider_override": r["provider_override"],
                "workspace_path": r["workspace_path"],
                "project_id": r["project_id"],
                "consecutive_failures": _int0(r["consecutive_failures"]),
                "body": _snippet(r["body"], 400),
            })

        events = []
        event_sql = (
            "SELECT e.id, e.task_id, e.run_id, e.kind, e.payload, e.created_at, t.title "
            "FROM task_events e LEFT JOIN tasks t ON t.id = e.task_id "
            "ORDER BY e.created_at DESC LIMIT ?"
        )
        for r in conn.execute(event_sql, (20,)):
            events.append({
                "id": r["id"],
                "task_id": r["task_id"],
                "task_title": r["title"],
                "run_id": r["run_id"],
                "kind": r["kind"],
                "payload": _snippet(r["payload"], 400),
                "created_at": _iso_col(r["created_at"], ev_mult),
            })

        return {
            "ok": True,
            "source": str(KANBAN_DB),
            "table": "tasks",
            "filter": {"status": status},
            "timestamp_units": {"tasks.created_at": _detect_ts_unit(conn, "kanban", "tasks", "created_at").get("unit"),
                                "task_events.created_at": _detect_ts_unit(conn, "kanban", "task_events", "created_at").get("unit")},
            "count": len(items),
            "limit": limit,
            "by_status": by_status,
            "total_tasks": sum(by_status.values()),
            "items": items,
            "recent_events": events,
            "recent_events_limit": 20,
        }
    except sqlite3.Error as exc:
        raise ToolError("kanban.db query failed: %s" % exc, "db_error") from exc
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Tool 4: ops_health
# ---------------------------------------------------------------------------

def _probe_ts(conn: sqlite3.Connection, db_key: str, table: str, col: str) -> dict:
    info = _detect_ts_unit(conn, db_key, table, col)
    unit = info.get("unit", "s")
    mult = UNIT_MULT.get(unit, 1.0)
    mn, mx = info.get("min"), info.get("max")
    return {
        "unit": unit,
        "detected": info.get("detected"),
        "samples": info.get("samples"),
        "min_raw": mn,
        "max_raw": mx,
        "min_iso": _iso(mn * mult) if mn is not None else None,
        "max_iso": _iso(mx * mult) if mx is not None else None,
        "error": info.get("error"),
    }


def _health_block(opener, db_path: Path, db_key: str, tables: tuple, ts_probes: tuple) -> dict:
    block: dict[str, Any] = {
        "ok": True, "path": str(db_path), "size_bytes": None,
        "tables": {}, "timestamps": {},
    }
    try:
        block["size_bytes"] = db_path.stat().st_size
    except OSError:
        pass
    try:
        conn = opener()
    except ToolError as exc:
        return {**block, "ok": False, "error": str(exc), "error_code": exc.code}
    except Exception as exc:  # noqa: BLE001 - health must never raise
        return {**block, "ok": False, "error": str(exc), "error_code": "db_unavailable"}
    try:
        for table in tables:
            try:
                count = conn.execute('SELECT COUNT(*) FROM "%s"' % table).fetchone()[0]
                block["tables"][table] = {"rows": _int0(count)}
            except sqlite3.Error as exc:
                block["tables"][table] = {"rows": None, "error": str(exc)}
        for table, col in ts_probes:
            block["timestamps"][table + "." + col] = _probe_ts(conn, db_key, table, col)
    except Exception as exc:  # noqa: BLE001
        block["ok"] = False
        block["error"] = str(exc)
        block["error_code"] = "db_error"
    finally:
        conn.close()
    return block


def _t_ops_health(args: dict) -> dict:
    state = _health_block(
        _open_state, STATE_DB, "state",
        ("sessions", "session_model_usage", "messages"),
        (("sessions", "started_at"), ("sessions", "last_activity_at"),
         ("session_model_usage", "last_seen"), ("messages", "timestamp")),
    )
    if state.get("ok"):
        try:
            conn = _open_state()
            try:
                mult = _unit_mult(conn, "state", "sessions", "started_at")
                row = conn.execute(
                    "SELECT MIN(started_at) AS mn, MAX(started_at) AS mx, "
                    "MIN(COALESCE(last_activity_at, started_at)) AS amn, "
                    "MAX(COALESCE(last_activity_at, started_at)) AS amx FROM sessions"
                ).fetchone()
                state["session_window"] = {
                    "oldest_started_at": _iso_col(row["mn"], mult),
                    "newest_started_at": _iso_col(row["mx"], mult),
                    "oldest_activity_at": _iso_col(row["amn"], mult),
                    "newest_activity_at": _iso_col(row["amx"], mult),
                }
            finally:
                conn.close()
        except (ToolError, sqlite3.Error) as exc:
            state["session_window"] = {"error": str(exc)}

    kanban = _health_block(
        _open_kanban, KANBAN_DB, "kanban",
        ("tasks", "task_events"),
        (("tasks", "created_at"), ("task_events", "created_at")),
    )

    return {
        "ok": bool(state.get("ok")) and bool(kanban.get("ok")),
        "now": _iso(time.time()),
        "now_epoch_seconds": time.time(),
        "timezone": "+08:00 (Asia/Shanghai)",
        "timestamp_policy": (
            "Every sampled time column is classified from its raw magnitude as "
            "Unix epoch seconds / milliseconds / microseconds / nanoseconds; the "
            "detected per-(table,column) unit is cached and used to normalize all "
            "epoch math. All ISO output is rendered in UTC+08:00."
        ),
        "databases": {"state": state, "kanban": kanban},
    }

# ---------------------------------------------------------------------------
# MCP tool declarations
# ---------------------------------------------------------------------------

def _obj(props: dict, required: list | None = None) -> dict:
    schema: dict[str, Any] = {"type": "object", "properties": props, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


TOOLS: list[dict] = [
    {
        "name": "usage_summary",
        "description": (
            "Hermes token/cost usage summary over a time window, read from "
            "state.db table session_model_usage. total_tokens = input_tokens + output_tokens; "
            "cache_read_tokens / cache_write_tokens / reasoning_tokens are reported separately "
            "and are NOT part of total_tokens. group_by: model | day (UTC+08) | source | "
            "session | none. Window filter = COALESCE(last_seen, first_seen)."
        ),
        "inputSchema": _obj({
            "since_days": {"type": "integer", "minimum": 0, "maximum": 3650, "default": 7,
                           "description": "Look-back window in days (0 = now onwards)."},
            "group_by": {"type": "string", "enum": list(GROUP_BY_CHOICES), "default": "model",
                         "description": "Grouping dimension: model | day | source | session | none."},
        }),
    },
    {
        "name": "sessions_list",
        "description": (
            "Recent Hermes sessions (state.db table sessions) ordered by total_tokens DESC. "
            "total_tokens = input_tokens + output_tokens. Window filter = "
            "COALESCE(last_activity_at, started_at); source matches exactly or by prefix, "
            "model matches as a substring."
        ),
        "inputSchema": _obj({
            "since_days": {"type": "integer", "minimum": 0, "maximum": 3650, "default": 7},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20},
            "source": {"type": "string", "description": "Exact source or prefix, e.g. hermes: or hermes:mybot."},
            "model": {"type": "string", "description": "Substring match on the session model."},
            "min_tokens": {"type": "integer", "minimum": 0,
                           "description": "Only sessions with input_tokens + output_tokens >= this value."},
        }),
    },
    {
        "name": "tasks_list",
        "description": (
            "Kanban tasks (kanban.db table tasks) plus by_status counts and the 20 most "
            "recent task_events. Timestamps are returned as UTC+08:00 ISO8601."
        ),
        "inputSchema": _obj({
            "status": {"type": "string", "description": "Exact task status filter, e.g. blocked."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
        }),
    },
    {
        "name": "ops_health",
        "description": (
            "Read-only reachability and freshness report for state.db and kanban.db: "
            "row counts, oldest/newest session timestamps, and the detected timestamp unit "
            "for every time column. Never writes and never raises."
        ),
        "inputSchema": _obj({}),
    },
]

_DISPATCH = {
    "usage_summary": _t_usage_summary,
    "sessions_list": _t_sessions_list,
    "tasks_list": _t_tasks_list,
    "ops_health": _t_ops_health,
}

INSTRUCTIONS = (
    "Hermes ops bridge (read-only). usage_summary aggregates token/cost usage from "
    "state.db.session_model_usage; total_tokens means input_tokens + output_tokens "
    "(cache and reasoning tokens are listed separately). sessions_list returns recent "
    "sessions ordered by total_tokens; tasks_list returns kanban tasks and recent events; "
    "ops_health reports data-source reachability and the detected timestamp units. "
    "All timestamps are ISO8601 in UTC+08:00. Every tool returns a JSON object inside "
    "the text content block."
)

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 / MCP framing
# ---------------------------------------------------------------------------

def _jsonrpc_result(msg_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _jsonrpc_error(msg_id: Any, code: int, message: str, data: Any = None) -> dict:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": err}


def _tool_result(payload: dict) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "isError": False,
    }


def _tool_error(message: str, code: str) -> dict:
    body = {"success": False, "error": message, "error_code": code}
    return {
        "content": [{"type": "text", "text": json.dumps(body, ensure_ascii=False)}],
        "isError": True,
    }


def _handle_tools_call(params: Any) -> dict:
    if not isinstance(params, dict):
        raise ToolError("params must be an object", "bad_request")
    name = params.get("name")
    if not isinstance(name, str) or name not in _DISPATCH:
        raise ToolError("unknown tool: %r" % (name,), "unknown_tool")
    arguments = params.get("arguments")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ToolError("arguments must be an object", "bad_request")
    return _DISPATCH[name](arguments)


def handle_message(msg: Any) -> dict | None:
    """Return a JSON-RPC response object, or None for notifications."""
    if not isinstance(msg, dict):
        return _jsonrpc_error(None, -32600, "Invalid Request")
    method = msg.get("method")
    msg_id = msg.get("id")
    has_id = "id" in msg

    if not isinstance(method, str) or not method:
        return _jsonrpc_error(msg_id, -32600, "Invalid Request") if has_id else None

    try:
        if method == "initialize":
            return _jsonrpc_result(msg_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": INSTRUCTIONS,
            })
        if method == "ping":
            return _jsonrpc_result(msg_id, {})
        if method == "tools/list":
            return _jsonrpc_result(msg_id, {"tools": TOOLS})
        if method == "tools/call":
            try:
                result = _handle_tools_call(msg.get("params"))
            except ToolError as exc:
                log.warning("tool call failed: %s", exc)
                return _jsonrpc_result(msg_id, _tool_error(str(exc), exc.code))
            except Exception as exc:  # noqa: BLE001 - never crash the server
                log.error("tool call crashed: %s\n%s", exc, traceback.format_exc())
                return _jsonrpc_result(msg_id, _tool_error("internal error: %s" % exc, "internal_error"))
            return _jsonrpc_result(msg_id, _tool_result(result))
        if method.startswith("notifications/"):
            return None
        if not has_id:
            return None
        return _jsonrpc_error(msg_id, -32601, "Method not found: %s" % method)
    except Exception as exc:  # noqa: BLE001
        log.error("internal error on %s: %s\n%s", method, exc, traceback.format_exc())
        if not has_id:
            return None
        return _jsonrpc_error(msg_id, -32603, "Internal error: %s" % exc)


def _write_frame(obj: Any) -> None:
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.buffer.write(data.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def main() -> int:
    log.info("started (pid=%s, state_db=%s, kanban_db=%s)", os.getpid(), STATE_DB, KANBAN_DB)
    stdin = sys.stdin.buffer
    for raw in stdin:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as exc:  # noqa: BLE001
            _write_frame(_jsonrpc_error(None, -32700, "Parse error: %s" % exc))
            continue

        if isinstance(msg, list):
            responses = [r for r in (handle_message(m) for m in msg) if r is not None]
            if responses:
                _write_frame(responses)
            continue

        response = handle_message(msg)
        if response is not None:
            _write_frame(response)
    log.info("stdin closed; exiting")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)