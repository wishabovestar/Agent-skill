#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dsh_memos_ingest.py — 把 dsh (DeepSeek Harness) 会话历史摄取进 Hermes MemOS 记忆库。

目标库: D:\\hermes\\hermes-data\\profiles\\mybot\\knowledge_base\\memos_vec.db
  memos_body(rowid, session_id, message_id, role, content, session_title, source, created_at REAL, token_count)
  memos_fts (external-content fts5)
  memos_meta(key TEXT PRIMARY KEY, value TEXT)

安全红线
  * 只删除/写入 source LIKE 'dsh:%' 的行; hermes:* 行必须原样存活。
  * 幂等: 自然键 = (source, session_id, message_id); 重灌单个会话前只删该会话的 dsh 行。
  * 首次写前把 memos_vec.db 备份为 memos_vec.db.bak_predsh_<ts>(同目录, 仅一份)。
  * 每次写事务前后校验 source LIKE 'hermes:%' 计数不变, 否则回滚。
  * 绝不使用参考实现里的 `DELETE FROM memos_body`(全表重建) 路径。

CLI
  python dsh_memos_ingest.py            # 默认增量(按 size+mtime 水位)
  python dsh_memos_ingest.py --full     # 忽略水位, 重灌全部 dsh 会话
  python dsh_memos_ingest.py --session <sessionId>
  python dsh_memos_ingest.py --stats    # 只读统计
  python dsh_memos_ingest.py --json     # 机器可读摘要
  python dsh_memos_ingest.py --dry-run  # 解析但不写库
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import zstandard as zstd
except Exception:  # pragma: no cover
    zstd = None

# ---------------------------------------------------------------- constants

DSH_HOME = Path(os.environ.get("DSH_HOME", r"C:\Users\Administrator\.dsh"))
SESSIONS_ROOT = DSH_HOME / "sessions"
DB_PATH = Path(r"D:\hermes\hermes-data\profiles\mybot\knowledge_base\memos_vec.db")

STATE_KEY = "dsh_ingest_state"
BACKUP_KEY = "dsh_backup_path"
MAX_CONTENT = 5000
TRUNC_SUFFIX = " ...[truncated]"

SOURCE_PREFIX = "dsh:"
HERMES_PREFIX = "hermes:"
LOG_FILENAME = "session.v4.jsonl.zstd"

# 只摄取这些事件; 其余(stream/request/*/step/*/turn/*/...)一律丢弃
RETAINED = {"user/message", "assistant/message", "tool/call", "tool/result", "system/message"}

# ------------------------------------------------------------------ decoding


def _scan_zstd_frames(buf: bytes) -> List[Tuple[int, int]]:
    """Structural scan for concatenated Zstandard frames (fallback for torn tails)."""
    magic_le = 0xFD2FB528
    frames: List[Tuple[int, int]] = []
    o = 0
    n = len(buf)
    while o < n:
        start = o
        if n - o < 4:
            break
        if int.from_bytes(buf[o:o + 4], "little") != magic_le:
            break
        o += 4
        if o >= n:
            break
        desc = buf[o]
        o += 1
        csf = desc >> 6
        single = bool(desc & 0x20)
        checksum = bool(desc & 0x04)
        dict_flag = desc & 0x03
        dict_bytes = 4 if dict_flag == 3 else dict_flag
        content_bytes = (1 if single else 0) if csf == 0 else (1 << csf)
        o += (0 if single else 1) + dict_bytes + content_bytes
        if o > n:
            break
        try:
            while True:
                if n - o < 3:
                    raise ValueError("short block header")
                block_header = int.from_bytes(buf[o:o + 3], "little")
                o += 3
                last_block = block_header & 1
                block_type = (block_header >> 1) & 0x03
                block_size = block_header >> 3
                payload = 1 if block_type == 0x01 else block_size
                if block_type == 0x03:
                    raise ValueError("reserved block type")
                if n - o < payload:
                    raise ValueError("short block payload")
                o += payload
                if last_block:
                    break
            if checksum:
                if n - o < 4:
                    raise ValueError("short checksum")
                o += 4
        except ValueError:
            o = start
            break
        frames.append((start, o))
    return frames


class DecodeError(RuntimeError):
    pass


def decode_session_text(raw: bytes) -> str:
    """Decode a `session.v4.jsonl.zstd` blob (concatenated zstd frames) to JSONL text."""
    if zstd is None:
        raise DecodeError("python `zstandard` is not importable in this interpreter")
    # Primary: the library walks concatenated frames natively.
    try:
        d = zstd.ZstdDecompressor()
        with d.stream_reader(io.BytesIO(raw), read_across_frames=True) as reader:
            data = reader.read()
        return data.decode("utf-8", "replace")
    except Exception:
        pass
    # Fallback: structural scan, skip a torn final frame (live session mid-write).
    parts: List[bytes] = []
    for start, end in _scan_zstd_frames(raw):
        try:
            parts.append(zstd.ZstdDecompressor().decompress(raw[start:end], max_output_size=1 << 30))
        except Exception:
            break
    if not parts:
        raise DecodeError("no complete zstd frame could be decoded")
    return b"".join(parts).decode("utf-8", "replace")


# --------------------------------------------------------------- extraction


def text_blocks(blocks: Any) -> str:
    """Concatenate fts-safe text from dsh ContentBlock[] (text blocks only)."""
    out: List[str] = []
    for b in blocks or []:
        if isinstance(b, dict) and b.get("type") == "text":
            t = b.get("text")
            if isinstance(t, str) and t:
                out.append(t)
    return "\n".join(out)


def parse_records(text: str) -> Tuple[Optional[dict], List[dict]]:
    header: Optional[dict] = None
    events: List[dict] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if header is None and isinstance(rec, dict) and rec.get("type") == "session":
            header = rec
            continue
        if isinstance(rec, dict) and "type" in rec:
            events.append(rec)
    return header, events


def session_title(events: Sequence[dict], slug: str) -> str:
    """Last session/title wins (fallback first, provider later); else slug / first-user prefix."""
    title: Optional[str] = None
    first_user: Optional[str] = None
    for e in events:
        if e.get("type") == "session/title":
            t = (e.get("data") or {}).get("title")
            if isinstance(t, str) and t.strip():
                title = t.strip()
        elif e.get("type") == "user/message" and first_user is None:
            t = text_blocks((e.get("data") or {}).get("content"))
            if t.strip():
                first_user = " ".join(t.split())
    if title:
        return title
    if first_user:
        return f"{slug} / {first_user[:40]}"
    return slug


def event_to_row(event: dict, session_id: str, source: str, title: str, fallback_ts: float) -> Optional[tuple]:
    """Map one dsh event to a memos_body row tuple, or None when it is not retained/empty."""
    typ = event.get("type")
    if typ not in RETAINED:
        return None
    d = event.get("data") or {}
    role: Optional[str] = None
    content: Optional[str] = None
    if typ == "user/message":
        role, content = "user", text_blocks(d.get("content"))
    elif typ == "assistant/message":
        role, content = "assistant", text_blocks((d.get("message") or {}).get("content"))
    elif typ == "tool/call":
        role = "assistant"
        content = f"[tool {d.get('name')}] {d.get('arguments')}"
    elif typ == "tool/result":
        role, content = "tool", text_blocks((d.get("message") or {}).get("content"))
    elif typ == "system/message":
        role, content = "system", text_blocks((d.get("message") or {}).get("content"))
    if not content or not content.strip():
        return None
    if len(content) > MAX_CONTENT:
        content = content[:MAX_CONTENT] + TRUNC_SUFFIX
    ts = event.get("time")
    created_at = (float(ts) / 1000.0) if isinstance(ts, (int, float)) and ts > 0 else float(fallback_ts)
    msg_id = event.get("seq")
    if not isinstance(msg_id, int):
        return None
    token_count = max(1, len(content) // 4)  # estimate: ~4 chars/token
    return (session_id, msg_id, role, content, title, source, created_at, token_count)


def build_session_rows(header: dict, events: List[dict], slug: str, fallback_ts: float) -> List[tuple]:
    sid_raw = header.get("id") or ""
    session_id = f"dsh:{sid_raw}"
    source = f"{SOURCE_PREFIX}{slug}"
    title = session_title(events, slug)
    rows: List[tuple] = []
    for e in events:
        row = event_to_row(e, session_id, source, title, fallback_ts)
        if row is not None:
            rows.append(row)
    return rows


# ------------------------------------------------------------- discovery


def discover_sessions(root: Path) -> List[Dict[str, Any]]:
    """Walk $DSH_HOME/sessions/<slug>/<sessionId>/session.v4.jsonl.zstd (read-only)."""
    found: List[Dict[str, Any]] = []
    if not root.is_dir():
        return found
    for path in sorted(root.rglob(LOG_FILENAME)):
        slug = path.parent.parent.name
        session_raw = path.parent.name
        st = path.stat()
        found.append({
            "sessionId": session_raw,
            "sessionKey": session_raw,
            "slug": slug,
            "source": f"{SOURCE_PREFIX}{slug}",
            "path": path,
            "size": st.st_size,
            "mtime": st.st_mtime,
        })
    return found


# ------------------------------------------------------------- db plumbing


def connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path), timeout=60)
    con.execute("PRAGMA busy_timeout=60000")
    con.execute("PRAGMA journal_mode=WAL")
    return con


def get_meta(con: sqlite3.Connection, key: str) -> Optional[str]:
    row = con.execute("SELECT value FROM memos_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute("INSERT OR REPLACE INTO memos_meta(key, value) VALUES (?, ?)", (key, value))


def load_state(con: sqlite3.Connection) -> Dict[str, Any]:
    raw = get_meta(con, STATE_KEY)
    if not raw:
        return {}
    try:
        state = json.loads(raw)
        return state if isinstance(state, dict) else {}
    except json.JSONDecodeError:
        return {}


def count_hermes(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COUNT(*) FROM memos_body WHERE source LIKE 'hermes:%'").fetchone()[0]


def count_dsh(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COUNT(*) FROM memos_body WHERE source LIKE 'dsh:%'").fetchone()[0]


def ensure_backup(con: sqlite3.Connection, db_path: Path, dry_run: bool) -> Tuple[Optional[Path], bool]:
    """Create the single required pre-dsh backup if none exists. Returns (path, created)."""
    existing = sorted(db_path.parent.glob(db_path.name + ".bak_predsh_*"))
    if existing:
        return existing[0], False
    if dry_run:
        return None, False
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = db_path.with_name(f"{db_path.name}.bak_predsh_{ts}")
    bck = sqlite3.connect(str(dest))
    try:
        with bck:
            con.backup(bck)  # online backup API: consistent even under WAL
    finally:
        bck.close()
    return dest, True


def ingest_one(con: sqlite3.Connection, sess: Dict[str, Any], rows: List[tuple],
               hermes_before: int) -> int:
    """Replace exactly one session's dsh rows, then verify the hermes invariant."""
    session_id = f"dsh:{sess['sessionId']}"
    cur = con.cursor()
    before = cur.execute(
        "SELECT COUNT(*) FROM memos_body WHERE source LIKE 'dsh:%' AND session_id=?", (session_id,)
    ).fetchone()[0]
    cur.execute("DELETE FROM memos_body WHERE source LIKE 'dsh:%' AND session_id=?", (session_id,))
    deleted = cur.rowcount
    if deleted != before:
        raise RuntimeError(f"delete guard tripped for {session_id}: deleted {deleted}, expected {before}")
    cur.executemany(
        "INSERT INTO memos_body(session_id, message_id, role, content, session_title, source, created_at, token_count)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    inserted = len(rows)
    hermes_after = count_hermes(con)
    if hermes_after != hermes_before:
        raise RuntimeError(
            f"INVARIANT VIOLATED: hermes rows {hermes_before} -> {hermes_after}; rolling back"
        )
    return inserted


# ---------------------------------------------------------------- stats


def print_stats(con: sqlite3.Connection, as_json: bool, state: Dict[str, Any]) -> dict:
    total = con.execute("SELECT COUNT(*) FROM memos_body").fetchone()[0]
    hermes = count_hermes(con)
    dsh = count_dsh(con)
    by_source = [
        {"source": s, "rows": n}
        for s, n in con.execute(
            "SELECT source, COUNT(*) FROM memos_body WHERE source LIKE 'dsh:%' GROUP BY source ORDER BY source"
        )
    ]
    by_role = [
        {"role": r, "rows": n}
        for r, n in con.execute(
            "SELECT role, COUNT(*) FROM memos_body WHERE source LIKE 'dsh:%' GROUP BY role ORDER BY role"
        )
    ]
    dsh_sessions = len(state) if state else 0
    info = {
        "db": str(DB_PATH),
        "total": total,
        "hermes_rows": hermes,
        "dsh_rows": dsh,
        "dsh_sessions_in_state": dsh_sessions,
        "dsh_by_source": by_source,
        "dsh_by_role": by_role,
        "backup_path": get_meta(con, BACKUP_KEY),
        "last_index": get_meta(con, "last_index"),
    }
    if as_json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"DB                 : {info['db']}")
        print(f"total rows         : {info['total']}")
        print(f"hermes:* rows      : {info['hermes_rows']}")
        print(f"dsh:* rows         : {info['dsh_rows']}")
        print(f"dsh sessions state : {info['dsh_sessions_in_state']}")
        print(f"backup             : {info['backup_path'] or '(none yet)'}")
        for r in by_source:
            print(f"  source {r['source']}: {r['rows']}")
        for r in by_role:
            print(f"  role   {r['role']}: {r['rows']}")
    return info


# ------------------------------------------------------------------- main


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Ingest dsh sessions into Hermes MemOS (memos_vec.db)")
    ap.add_argument("--full", action="store_true", help="ignore watermark, re-ingest every dsh session")
    ap.add_argument("--session", metavar="ID", help="ingest only this session id (forced)")
    ap.add_argument("--stats", action="store_true", help="print stats only, no writes")
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    ap.add_argument("--dry-run", action="store_true", help="parse but do not write")
    ap.add_argument("--db", default=str(DB_PATH), help="override db path (testing)")
    ap.add_argument("--sessions-root", default=str(SESSIONS_ROOT), help="override sessions root (testing)")
    args = ap.parse_args(argv)

    if zstd is None:
        print("FATAL: python `zstandard` is required in this interpreter", file=sys.stderr)
        return 2

    db_path = Path(args.db)
    sessions_root = Path(args.sessions_root)
    if not db_path.exists():
        print(f"FATAL: db not found: {db_path}", file=sys.stderr)
        return 2

    con = connect(db_path)
    summary: Dict[str, Any] = {"db": str(db_path), "mode": "stats" if args.stats else "ingest"}

    if args.stats:
        state = load_state(con)
        info = print_stats(con, args.json, state)
        con.close()
        return 0

    sessions = discover_sessions(sessions_root)
    state = load_state(con)
    hermes_before = count_hermes(con)
    summary.update({
        "sessions_found": len(sessions),
        "hermes_before": hermes_before,
        "dsh_before": count_dsh(con),
    })

    # decide which sessions to (re)ingest
    todo: List[Dict[str, Any]] = []
    skipped: List[str] = []
    for s in sessions:
        if args.session:
            if s["sessionId"] != args.session:
                continue
            todo.append(s)
            continue
        prev = state.get(s["sessionId"])
        if not args.full and isinstance(prev, dict) \
                and prev.get("size") == s["size"] and prev.get("mtime") == s["mtime"]:
            skipped.append(s["sessionId"])
            continue
        todo.append(s)

    if args.session and not todo:
        print(f"FATAL: session not found on disk: {args.session}", file=sys.stderr)
        con.close()
        return 2

    backup_path = None
    backup_created = False
    if todo and not args.dry_run:
        backup_path, backup_created = ensure_backup(con, db_path, args.dry_run)
        if backup_path:
            set_meta(con, BACKUP_KEY, str(backup_path))
            con.commit()
    summary["backup_path"] = str(backup_path) if backup_path else None
    summary["backup_created"] = backup_created

    print(f"== dsh -> MemOS ingest ({'DRY-RUN' if args.dry_run else 'WRITE'}) ==")
    if backup_path:
        print(f"BACKUP: {backup_path} ({'created' if backup_created else 'existing'})")
    print(f"db={db_path}")
    print(f"sessions found={len(sessions)}  to-ingest={len(todo)}  skipped(watermark)={len(skipped)}")
    print(f"hermes:* rows before = {hermes_before}")

    total_inserted = 0
    per_session: List[dict] = []
    errors: List[str] = []
    try:
        for s in todo:
            raw = s["path"].read_bytes()
            try:
                text = decode_session_text(raw)
            except DecodeError as exc:
                errors.append(f"{s['sessionId']}: decode failed: {exc}")
                continue
            header, events = parse_records(text)
            if header is None:
                errors.append(f"{s['sessionId']}: no session header")
                continue
            rows = build_session_rows(header, events, s["slug"], s["mtime"])
            retained = len(rows)
            if args.dry_run:
                total_inserted += retained
                per_session.append({"sessionId": s["sessionId"], "source": s["source"],
                                    "events": len(events), "rows": retained, "written": False})
                print(f"  [dry] {s['sessionId']} events={len(events)} rows={retained}")
                continue
            with con:  # one transaction per session + invariant assertion
                inserted = ingest_one(con, s, rows, hermes_before)
            total_inserted += inserted
            state[s["sessionId"]] = {
                "size": s["size"],
                "mtime": s["mtime"],
                "source": s["source"],
                "rows": inserted,
                "events": len(events),
                "ingested_at": datetime.now().isoformat(timespec="seconds"),
            }
            per_session.append({"sessionId": s["sessionId"], "source": s["source"],
                                "events": len(events), "rows": inserted, "written": True})
            print(f"  + {s['sessionId']} events={len(events)} rows={inserted} source={s['source']}")
    except Exception as exc:  # pragma: no cover
        con.rollback()
        print(f"FATAL: {exc}", file=sys.stderr)
        con.close()
        return 1

    if not args.dry_run:
        # persist watermark + rebuild the external-content FTS index
        with con:
            set_meta(con, STATE_KEY, json.dumps(state, ensure_ascii=False))
            if total_inserted > 0 or todo:
                con.execute("INSERT INTO memos_fts(memos_fts) VALUES('rebuild')")
        hermes_after = count_hermes(con)
        summary["hermes_after"] = hermes_after
        summary["invariant_ok"] = (hermes_after == hermes_before)
        if hermes_after != hermes_before:
            print(f"FATAL: hermes invariant broken {hermes_before} -> {hermes_after}", file=sys.stderr)
            con.close()
            return 1
        summary["dsh_after"] = count_dsh(con)
    else:
        summary["hermes_after"] = hermes_before
        summary["invariant_ok"] = True
        summary["dsh_after"] = summary["dsh_before"]

    summary.update({
        "sessions_ingested": len([p for p in per_session if p.get("written")]) if not args.dry_run else 0,
        "rows_inserted": total_inserted,
        "per_session": per_session,
        "skipped": skipped,
        "errors": errors,
    })
    print(f"rows inserted = {total_inserted}")
    print(f"hermes:* rows after  = {summary['hermes_after']}  (invariant {'OK' if summary['invariant_ok'] else 'BROKEN'})")
    if errors:
        print(f"errors = {len(errors)}")
        for e in errors:
            print("  ! " + e)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())