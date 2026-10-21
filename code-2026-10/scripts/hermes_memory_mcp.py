#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hermes_memory_mcp.py -- single-file stdio MCP server exposing the two Hermes
memory components on this profile to an external agent (dsh).

Components
----------
* MemOS  : SQLite/WAL + FTS5 conversation memory at
           <profile>/knowledge_base/memos_vec.db  (table memos_body + memos_fts).
           Search shape reuses scripts/memos_hybrid_search.py (BM25 -> char-ngram
           KNN rerank -> MMR), but the DB is opened READ-ONLY (mode=ro +
           PRAGMA query_only=ON) so this server never writes memos_vec.db.
* CortexMem : evolving 3-type graph (semantic/episodic/procedural) driven through
           the JSON CLI scripts/cortexmem_tool.py (subprocess, argv list, no shell).

Transport
---------
MCP 2024-11-05 over stdio, newline-delimited JSON-RPC 2.0.
stdout carries ONLY one JSON-RPC frame per line; all logging goes to stderr.

Launch (pure argv, no shell):
  "C:\\Users\\Administrator\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\python.exe"
  -u "D:\\hermes\\hermes-data\\profiles\\mybot\\scripts\\hermes_memory_mcp.py"

Env overrides (optional): HERMES_MEMORY_DB, HERMES_MEMORY_SCRIPTS,
HERMES_MEMORY_PYTHON, HERMES_MEMORY_TIMEOUT.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "hermes-memory"
SERVER_VERSION = "1.0.0"

SCRIPT_DIR = Path(__file__).resolve().parent
PROFILE_HOME = SCRIPT_DIR.parent

DEFAULT_DB = PROFILE_HOME / "knowledge_base" / "memos_vec.db"
DEFAULT_CORTEX_CWD = SCRIPT_DIR
CORTEX_TOOL = "cortexmem_tool.py"

DB_PATH = Path(os.environ["HERMES_MEMORY_DB"]) if os.environ.get("HERMES_MEMORY_DB") else DEFAULT_DB
CORTEX_CWD = Path(os.environ["HERMES_MEMORY_SCRIPTS"]) if os.environ.get("HERMES_MEMORY_SCRIPTS") else DEFAULT_CORTEX_CWD
PYTHON = os.environ.get("HERMES_MEMORY_PYTHON") or sys.executable or "python"
CORTEX_TIMEOUT = int(os.environ.get("HERMES_MEMORY_TIMEOUT", "60"))

MAX_CONTENT = 300
DEFAULT_SEARCH_K = 8
DEFAULT_RECALL_K = 5
KINDS = ("semantic", "episodic", "procedural")

# The reference pipeline (memos_hybrid_search.hybrid_search) hardcodes
# mmr_rerank(lambda_param=0.7, k). We mirror that exact value for the
# source-filtered path so both paths rank identically.
MMR_LAMBDA = 0.7
MMR_POOL_MULT = 2
BM25_POOL_MULT = 3

log = logging.getLogger("hermes-memory")
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("[hermes-memory] %(levelname)s %(message)s"))
    log.addHandler(_h)
log.setLevel(logging.INFO)
log.propagate = False

_mhs: Any = None
try:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    import memos_hybrid_search as _mhs  # noqa: E402 - reference module, __main__ guarded
except Exception as exc:
    log.warning("could not import memos_hybrid_search: %s", exc)


class ToolError(Exception):
    """Raised by a tool implementation; rendered as an MCP isError result."""

    def __init__(self, message: str, code: str = "memory_error") -> None:
        super().__init__(message)
        self.code = code


def _readonly_connect(db_path: Path) -> sqlite3.Connection:
    """Open the memory DB read-only. Prefer SQLite URI mode=ro; if the WAL/shm
    sidecars are unavailable, fall back to a normal handle immediately pinned to
    PRAGMA query_only=ON so no statement in this process can write."""
    uri = db_path.as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=15)
        conn.execute("PRAGMA query_only=ON")
        return conn
    except sqlite3.Error as exc:
        log.warning("read-only URI open failed (%s); falling back to query_only", exc)
        conn = sqlite3.connect(str(db_path), timeout=15)
        conn.execute("PRAGMA query_only=ON")
        return conn


def _fts_or_query(query: str) -> str:
    """Lenient fallback MATCH expression: each whitespace token quoted and OR-joined.

    FTS5's implicit operator is AND, which makes long natural-language or CJK
    queries return nothing. Only used when the strict query yielded zero rows."""
    import re as _re

    parts: list[str] = []
    for raw in _re.split(r"\s+", (query or "").strip()):
        cleaned = _re.sub(r"[^\w\u4e00-\u9fff\u3040-\u30ff]+", " ", raw, flags=_re.UNICODE).strip()
        for tok in cleaned.split():
            if tok:
                parts.append('"%s"' % tok.replace('"', ""))
    return " OR ".join(parts)


class ReadOnlyBM25:
    """Same search(query, k) -> list[dict] contract as the reference BM25Search,
    but strictly read-only and with an optional source filter."""

    def __init__(self, db_path: Path) -> None:
        self.conn = _readonly_connect(db_path)

    def _rows(self, match: str, k: int, source: str | None) -> list[tuple]:
        sql = (
            "SELECT b.rowid, b.session_id, b.message_id, b.role, b.content, "
            "b.session_title, b.source, b.created_at, b.token_count, rank "
            "FROM memos_fts f JOIN memos_body b ON f.rowid = b.rowid "
            "WHERE memos_fts MATCH ?"
        )
        params: list[Any] = [match]
        if source:
            sql += " AND (b.source = ? OR b.source LIKE ? || '%')"
            params.extend([source, source])
        sql += " ORDER BY rank LIMIT ?"
        params.append(k * 2)
        return self.conn.execute(sql, params).fetchall()

    def search(self, query: str, k: int = 10, source: str | None = None) -> list[dict]:
        if not query or not query.strip():
            return []
        strict = query.replace('"', '""')
        try:
            rows = self._rows(strict, k, source)
        except sqlite3.OperationalError as exc:
            log.warning("FTS strict MATCH failed (%s); retrying lenient", exc)
            rows = []
        if not rows:
            fallback = _fts_or_query(query)
            if fallback and fallback != strict:
                try:
                    rows = self._rows(fallback, k, source)
                except sqlite3.OperationalError as exc:
                    raise ToolError("FTS5 query failed: %s" % exc, "memos_query_error") from exc
        out: list[dict] = []
        for r in rows:
            rank = r[9]
            bm25_score = 1.0 / (1.0 + abs(rank)) if rank is not None else 0.5
            out.append({
                "rowid": r[0], "session_id": r[1], "message_id": r[2],
                "role": r[3], "content": (r[4] or "")[:MAX_CONTENT],
                "session_title": r[5], "source": r[6], "created_at": r[7],
                "token_count": r[8], "bm25_score": round(bm25_score, 4),
            })
        return out[:k]

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


def _iso(ts: Any) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _snippet(text: Any, limit: int = MAX_CONTENT) -> str:
    s = "" if text is None else str(text)
    return s[:limit]

def _hybrid_search(query: str, k: int, source: str | None) -> list[dict]:
    if _mhs is None:
        raise ToolError(
            "memos_hybrid_search.py could not be imported; check HERMES_MEMORY_SCRIPTS",
            "memos_unavailable",
        )
    bm25 = ReadOnlyBM25(DB_PATH)
    try:
        if source:
            rough = bm25.search(query, k=k * BM25_POOL_MULT, source=source)
            if not rough:
                return []
            reranked = _mhs.knn_search(query, rough, k=k * MMR_POOL_MULT)
            return _mhs.mmr_rerank(reranked, MMR_LAMBDA, k)
        return _mhs.hybrid_search(bm25, query, k=k)
    finally:
        bm25.close()


def _t_memory_search(args: dict) -> dict:
    query = _require_text(args, "query")
    k = _int_arg(args, "k", DEFAULT_SEARCH_K, 1, 50)
    source = args.get("source")
    source = str(source).strip() if source not in (None, "") else None
    results = _hybrid_search(query, k, source)
    return {
        "query": query, "k": k, "source": source,
        "hit_count": len(results),
        "results": [{
            "content": _snippet(r.get("content")),
            "role": r.get("role"),
            "session_title": r.get("session_title"),
            "source": r.get("source"),
            "created_at": _iso(r.get("created_at")),
            "score": r.get("hybrid_score", r.get("bm25_score")),
            "bm25_score": r.get("bm25_score"),
            "vector_score": r.get("vector_score"),
            "session_id": r.get("session_id"),
            "rowid": r.get("rowid"),
        } for r in results],
    }


def _run_cortexmem(payload: dict, timeout: int | None = None) -> dict:
    cmd = [PYTHON, CORTEX_TOOL, json.dumps(payload, ensure_ascii=False)]
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    try:
        proc = subprocess.run(
            cmd, cwd=str(CORTEX_CWD), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout or CORTEX_TIMEOUT, env=env,
        )
    except FileNotFoundError as exc:
        raise ToolError("python interpreter not found: %s" % exc, "cortexmem_unavailable") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolError("CortexMem call timed out after %ss" % (timeout or CORTEX_TIMEOUT),
                        "cortexmem_timeout") from exc
    if proc.returncode != 0:
        raise ToolError(
            "cortexmem_tool.py exited %s: %s" % (proc.returncode, (proc.stderr or "").strip()[:500]),
            "cortexmem_failed",
        )
    out = (proc.stdout or "").strip()
    if not out:
        raise ToolError("cortexmem_tool.py produced no stdout", "cortexmem_bad_output")
    try:
        data = json.loads(out.splitlines()[-1])
    except Exception as exc:
        raise ToolError("cortexmem_tool.py output is not JSON: %s" % out[:300],
                        "cortexmem_bad_output") from exc
    if not isinstance(data, dict):
        raise ToolError("cortexmem_tool.py returned non-object JSON", "cortexmem_bad_output")
    return data


def _t_experience_recall(args: dict) -> dict:
    query = _require_text(args, "query")
    k = _int_arg(args, "k", DEFAULT_RECALL_K, 1, 50)
    data = _run_cortexmem({"action": "query", "query": query, "top_k": k})
    if not data.get("success"):
        raise ToolError(data.get("error") or "CortexMem query failed", "cortexmem_error")
    payload = data.get("data") or {}
    results = [{
        "content": _snippet(r.get("content")),
        "type": r.get("type"),
        "state": r.get("state"),
        "score": r.get("score"),
    } for r in (payload.get("results") or [])]
    return {
        "query": query, "k": k,
        "hit_count": int(payload.get("hit_count", len(results)) or 0),
        "results": results,
    }


def _t_memory_write(args: dict) -> dict:
    content = _require_text(args, "content")
    kind = str(args.get("kind") or "semantic").strip().lower()
    if kind not in KINDS:
        raise ToolError("kind must be one of %s" % (", ".join(KINDS)), "bad_argument")
    tags = args.get("tags")
    if tags is not None and not isinstance(tags, list):
        raise ToolError("tags must be an array of strings", "bad_argument")
    data = _run_cortexmem({"action": "add", "content": content, "type": kind})
    if not data.get("success"):
        raise ToolError(data.get("error") or "CortexMem add failed", "cortexmem_error")
    payload = data.get("data") or {}
    return {
        "id": payload.get("id"),
        "added": payload.get("added"),
        "nodes": payload.get("nodes"),
        "type": kind,
        "tags": tags or [],
        "tags_applied": False,
        "note": ("cortexmem_tool.py add exposes no node id and CortexMem has no tag "
                 "field, so id/tags are reported honestly as unavailable/not persisted."),
    }


def _t_memory_stats(args: dict) -> dict:
    memos: dict[str, Any] = {"db": str(DB_PATH)}
    try:
        conn = _readonly_connect(DB_PATH)
        try:
            by_source = {row[0]: row[1] for row in conn.execute(
                "SELECT source, COUNT(*) FROM memos_body GROUP BY source ORDER BY 2 DESC, 1")}
            memos["by_source"] = by_source
            memos["total"] = sum(by_source.values())
            row = conn.execute("SELECT value FROM memos_meta WHERE key='last_index'").fetchone()
            memos["last_index"] = row[0] if row else None
        finally:
            conn.close()
    except Exception as exc:
        memos["error"] = str(exc)

    cortex: dict[str, Any] = {"available": False}
    try:
        data = _run_cortexmem({"action": "stats"})
        if data.get("success"):
            cortex = {"available": True, **(data.get("data") or {})}
        else:
            cortex = {"available": False, "error": data.get("error") or "stats failed"}
    except ToolError as exc:
        cortex = {"available": False, "error": str(exc)}
    except Exception as exc:
        cortex = {"available": False, "error": str(exc)}
    return {"memos": memos, "cortexmem": cortex}


def _require_text(args: dict, key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolError("%s must be a non-empty string" % key, "bad_argument")
    return value.strip()


def _int_arg(args: dict, key: str, default: int, low: int, high: int) -> int:
    value = args.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolError("%s must be an integer" % key, "bad_argument")
    ivalue = int(value)
    if ivalue < low or ivalue > high:
        raise ToolError("%s must be between %d and %d" % (key, low, high), "bad_argument")
    return ivalue

TOOLS: list[dict] = [
    {
        "name": "memory_search",
        "description": ("Search Hermes conversation memory (MemOS: FTS5 BM25 + char-ngram "
                        "KNN rerank + MMR). Returns ranked real messages with session title, "
                        "role, source and ISO timestamp."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language or keyword query."},
                "k": {"type": "integer", "minimum": 1, "maximum": 50, "default": DEFAULT_SEARCH_K,
                      "description": "Number of hits to return."},
                "source": {"type": "string",
                           "description": "Optional source filter: prefix hermes: / dsh: or an exact source such as hermes:mybot."},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "experience_recall",
        "description": ("Recall distilled experiences/skills from CortexMem (semantic / episodic / "
                        "procedural graph). Returns content, type, state and score; hit_count is 0 "
                        "on an empty graph."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Experience / skill / fact to recall."},
                "k": {"type": "integer", "minimum": 1, "maximum": 50, "default": DEFAULT_RECALL_K,
                      "description": "Number of experiences to return."},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "memory_write",
        "description": ("Store a durable experience/node into CortexMem. kind is the node type: "
                        "semantic (facts), episodic (events) or procedural (how-to)."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The experience to persist."},
                "kind": {"type": "string", "enum": list(KINDS), "default": "semantic"},
                "tags": {"type": "array", "items": {"type": "string"},
                         "description": "Optional labels (accepted for API compatibility; CortexMem has no tag field, so they are echoed but not persisted)."},
            },
            "required": ["content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "memory_stats",
        "description": ("Memory health: MemOS row count grouped by source + last_index, and CortexMem "
                        "nodes/edges/types when reachable."),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]

_DISPATCH = {
    "memory_search": _t_memory_search,
    "experience_recall": _t_experience_recall,
    "memory_write": _t_memory_write,
    "memory_stats": _t_memory_stats,
}

INSTRUCTIONS = (
    "Hermes memory bridge. Use memory_search to recall past conversation turns "
    "(MemOS) and experience_recall for distilled skills/experiences (CortexMem). "
    "Use memory_write to persist a new experience. All tools return a JSON object "
    "inside the text content block."
)


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
    arguments = params.get("arguments") or {}
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
            return _jsonrpc_result(msg_id, _tool_result(result))
        if method.startswith("notifications/"):
            return None
        if not has_id:
            return None
        return _jsonrpc_error(msg_id, -32601, "Method not found: %s" % method)
    except Exception as exc:
        log.error("internal error on %s: %s\n%s", method, exc, traceback.format_exc())
        if not has_id:
            return None
        return _jsonrpc_error(msg_id, -32603, "Internal error: %s" % exc)


def _write_frame(obj: Any) -> None:
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.buffer.write(data.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def main() -> int:
    log.info("started (pid=%s, db=%s, cortex_cwd=%s, python=%s)",
             os.getpid(), DB_PATH, CORTEX_CWD, PYTHON)
    stdin = sys.stdin.buffer
    for raw in stdin:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as exc:
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
