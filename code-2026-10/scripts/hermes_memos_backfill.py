#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hermes_memos_backfill.py — 用 mybot 的 state.db 回填干净的 `hermes:mybot` 记忆行。

背景
  现有 `hermes:mybot` 18,686 行只覆盖 2026-07-05..2026-08-01、message_id 2..36068,
  但 state.db 里 id<=36068 且 >=50 字符的只有 11,929 条 —— 说明这批行是从别的 profile
  (参考实现默认 qqbot3) 建的,被贴错了 source 标签。本脚本:
    1) 先把这批贴错的行原地重贴为 `hermes:mybot@legacy`(零丢失、可回滚);
    2) 再从 state.db 按新口径重建干净的 `hermes:mybot`。

安全红线(与 dsh_memos_ingest.py 一致)
  * 绝不删除/修改 `dsh:%` 与 `ops:%` 行;每批事务内断言二者计数不变,否则回滚。
  * 只动 `hermes:mybot` / `hermes:mybot@legacy`。
  * 运行前先备份 memos_vec.db 为 `memos_vec.db.bak_hermesbackfill_<ts>`(同目录、仅一份)。
  * 幂等:自然键 (source, session_id, message_id);已存在的 message_id 跳过。
  * 结束 `INSERT INTO memos_fts(memos_fts) VALUES('rebuild')`,并用 MATCH 验证。
  * state.db 用只读 URI 打开,绝不复制整库、绝不写。

筛选口径
  content IS NOT NULL AND length(trim(content)) > 0
  AND ( length(content) > 50 OR role = 'user' )     -- user 不设长度门槛

CLI
  python hermes_memos_backfill.py                     # = --full
  python hermes_memos_backfill.py --stats
  python hermes_memos_backfill.py --since-id 36068
  python hermes_memos_backfill.py --max-id 112324     # 上界(确定性重跑用)
  python hermes_memos_backfill.py --batch 5000
  python hermes_memos_backfill.py --dry-run --json
  python hermes_memos_backfill.py --skip-legacy-retag
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

STATE_DB = Path(r"D:\hermes\hermes-data\profiles\mybot\state.db")
MEMOS_DB = Path(r"D:\hermes\hermes-data\profiles\mybot\knowledge_base\memos_vec.db")

NEW_SOURCE = "hermes:mybot"
LEGACY_SOURCE = "hermes:mybot@legacy"
STATE_KEY = "hermes_backfill_state"
BACKUP_SUFFIX = ".bak_hermesbackfill_"
MAX_CONTENT = 5000
TRUNC_SUFFIX = " ...[truncated]"

FILTER = ("m.content IS NOT NULL AND length(trim(m.content)) > 0 "
          "AND ( length(m.content) > 50 OR m.role = 'user' )")

SUSPECT_PREFIXES = ["[IMPORTANT:", "[CONTEXT COMPACTION", "<untrusted", "SYSTEM:"]

# ---------------------------------------------------------------- helpers


def ro_state(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect("file:" + str(path).replace("\\", "/") + "?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def count_sources(con: sqlite3.Connection, like: str) -> int:
    return con.execute("SELECT COUNT(*) FROM memos_body WHERE source LIKE ?", (like,)).fetchone()[0]


def meta_get(con: sqlite3.Connection, key: str) -> Optional[str]:
    r = con.execute("SELECT value FROM memos_meta WHERE key=?", (key,)).fetchone()
    return r[0] if r else None


def meta_set(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute("INSERT OR REPLACE INTO memos_meta(key,value) VALUES (?,?)", (key, value))


def ensure_backup(con: sqlite3.Connection, db_path: Path, dry_run: bool) -> Tuple[Optional[Path], bool]:
    if dry_run:
        return None, False
    existing = sorted(db_path.parent.glob(db_path.name + BACKUP_SUFFIX + "*"))
    if existing:
        return existing[0], False
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = db_path.with_name(f"{db_path.name}{BACKUP_SUFFIX}{ts}")
    bck = sqlite3.connect(str(dest))
    try:
        with bck:
            con.backup(bck)
    finally:
        bck.close()
    return dest, True


def snapshot_sha(con: sqlite3.Connection, db_path: Path, tag: str) -> Tuple[Path, str]:
    """Consistent snapshot via the online backup API (covers WAL) + its sha256."""
    dest = db_path.with_name(f"{db_path.name}.snap_{tag}")
    if dest.exists():
        dest.unlink()
    bck = sqlite3.connect(str(dest))
    try:
        with bck:
            con.backup(bck)
    finally:
        bck.close()
    return dest, sha256_file(dest)


# ------------------------------------------------------------- statistics


def collect_stats(state: sqlite3.Connection, memos: sqlite3.Connection,
                  since_id: Optional[int], max_id: Optional[int]) -> Dict[str, Any]:
    where = [FILTER]
    params: List[Any] = []
    if since_id is not None:
        where.append("m.id > ?"); params.append(since_id)
    if max_id is not None:
        where.append("m.id <= ?"); params.append(max_id)
    w = " AND ".join(where)

    by_role = {r[0]: r[1] for r in state.execute(
        f"SELECT m.role, COUNT(*) FROM messages m WHERE {w} GROUP BY m.role ORDER BY 2 DESC", params)}
    eligible = sum(by_role.values())

    suspect = {}
    for p in SUSPECT_PREFIXES:
        suspect[p] = state.execute(
            f"SELECT COUNT(*) FROM messages m WHERE {w} AND m.role='user' AND m.content LIKE ?",
            [*params, p + "%"]).fetchone()[0]
    user_total = by_role.get("user", 0)
    suspect_total = state.execute(
        f"SELECT COUNT(*) FROM messages m WHERE {w} AND m.role='user' AND ("
        + " OR ".join(["m.content LIKE ?"] * len(SUSPECT_PREFIXES)) + ")",
        [*params, *[p + "%" for p in SUSPECT_PREFIXES]]).fetchone()[0]

    rng = state.execute(
        f"SELECT MIN(m.timestamp), MAX(m.timestamp) FROM messages m WHERE {w}", params).fetchone()
    existing = memos.execute(
        "SELECT COUNT(*), MIN(message_id), MAX(message_id) FROM memos_body WHERE source=?",
        (NEW_SOURCE,)).fetchone()
    legacy = memos.execute(
        "SELECT COUNT(*), MIN(message_id), MAX(message_id) FROM memos_body WHERE source=?",
        (LEGACY_SOURCE,)).fetchone()
    return {
        "eligible": eligible,
        "by_role": by_role,
        "user_total": user_total,
        "suspect_injection": suspect,
        "suspect_injection_total": suspect_total,
        "state_ts_min": rng[0], "state_ts_max": rng[1],
        "new_source_existing": existing[0],
        "new_source_id_range": [existing[1], existing[2]],
        "legacy_rows": legacy[0],
        "legacy_id_range": [legacy[1], legacy[2]],
        "dsh_rows": count_sources(memos, "dsh:%"),
        "ops_rows": count_sources(memos, "ops:%"),
        "body_rows": memos.execute("SELECT COUNT(*) FROM memos_body").fetchone()[0],
        "fts_rows": memos.execute("SELECT COUNT(*) FROM memos_fts").fetchone()[0],
    }


# ---------------------------------------------------------------- retag


def legacy_retag(memos: sqlite3.Connection, state: dict, skip: bool, dry_run: bool) -> int:
    """Move the mislabeled `hermes:mybot` rows to `hermes:mybot@legacy` exactly once."""
    legacy_now = memos.execute(
        "SELECT COUNT(*) FROM memos_body WHERE source=?", (LEGACY_SOURCE,)).fetchone()[0]
    done_flag = state.get("legacy_retag_done") is True
    if skip:
        return 0
    if done_flag or legacy_now > 0:
        return 0
    n = memos.execute("SELECT COUNT(*) FROM memos_body WHERE source=?", (NEW_SOURCE,)).fetchone()[0]
    if n == 0:
        return 0
    if dry_run:
        return n
    cur = memos.execute("UPDATE memos_body SET source=? WHERE source=?", (LEGACY_SOURCE, NEW_SOURCE))
    return cur.rowcount


# ------------------------------------------------------------------ main


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Backfill clean hermes:mybot rows from mybot state.db")
    ap.add_argument("--full", action="store_true", help="rebuild hermes:mybot (default)")
    ap.add_argument("--since-id", type=int, default=None, help="only messages.id > N")
    ap.add_argument("--max-id", type=int, default=None, help="only messages.id <= N (bound a run)")
    ap.add_argument("--batch", type=int, default=5000, help="rows per transaction (default 5000)")
    ap.add_argument("--stats", action="store_true", help="print counts only, no writes")
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    ap.add_argument("--dry-run", action="store_true", help="compute and print, write nothing")
    ap.add_argument("--skip-legacy-retag", action="store_true", help="skip the legacy retag step")
    ap.add_argument("--db", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--state-db", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    global MEMOS_DB, STATE_DB
    if args.db:
        MEMOS_DB = Path(args.db)
    if args.state_db:
        STATE_DB = Path(args.state_db)

    t0 = time.time()
    summary: Dict[str, Any] = {"db": str(MEMOS_DB), "state_db": str(STATE_DB),
                               "since_id": args.since_id, "max_id": args.max_id,
                               "batch": args.batch, "dry_run": args.dry_run}
    memos = sqlite3.connect(str(MEMOS_DB), timeout=60)
    memos.execute("PRAGMA busy_timeout=60000")
    state_con = ro_state(STATE_DB)
    try:
        st_before = collect_stats(state_con, memos, args.since_id, args.max_id)
        summary["before"] = st_before
        summary["sha256_file_before"] = sha256_file(MEMOS_DB)

        if args.stats:
            out = {"stats": st_before}
            if args.json:
                print(json.dumps(out, ensure_ascii=False, indent=2))
            else:
                _print_stats(st_before, MEMOS_DB)
            return 0

        dsh_before = st_before["dsh_rows"]
        ops_before = st_before["ops_rows"]
        legacy_before = st_before["legacy_rows"]

        # 1) backup + pre snapshot
        backup, created = ensure_backup(memos, MEMOS_DB, args.dry_run)
        if backup:
            summary["backup"] = str(backup)
            summary["backup_created"] = created
        _, summary["snapshot_sha256_before"] = (None, "") if args.dry_run else snapshot_sha(memos, MEMOS_DB, "before")

        # 2) legacy retag (exactly once)
        state = {}
        raw = meta_get(memos, STATE_KEY)
        if raw:
            try:
                state = json.loads(raw)
            except json.JSONDecodeError:
                state = {}
        if not args.dry_run:
            with memos:
                retagged = legacy_retag(memos, state, args.skip_legacy_retag, False)
                if retagged:
                    state["legacy_retag_done"] = True
                    state["legacy_retagged_rows"] = retagged
        else:
            retagged = legacy_retag(memos, state, args.skip_legacy_retag, True)
        summary["legacy_retagged"] = retagged
        summary["legacy_retag_skipped"] = (retagged == 0)

        # 3) backfill new hermes:mybot, skipping existing message_ids
        # natural key = (source, session_id, message_id).  After a real legacy retag
        # there are no NEW_SOURCE rows left; in dry-run we simulate that retag.
        existing_keys = set()
        if not (args.dry_run and retagged > 0):
            for r in memos.execute("SELECT session_id, message_id FROM memos_body WHERE source=?", (NEW_SOURCE,)):
                existing_keys.add((r[0], r[1]))
        summary["existing_message_ids"] = len(existing_keys)

        print(f"== hermes:mybot backfill ({'DRY-RUN' if args.dry_run else 'WRITE'}) ==")
        if summary.get("backup"):
            print(f"BACKUP: {summary['backup']}")
        print(f"eligible={st_before['eligible']} by_role={st_before['by_role']}")
        print(f"legacy retagged={retagged}  existing hermes:mybot natural keys={len(existing_keys)}")
        print(f"dsh:%={dsh_before} ops:%={ops_before} (must stay constant)")

        inserted = 0
        seen = 0
        last_id = args.since_id if args.since_id is not None else 0
        rows_per_batch = max(1, args.batch)
        while True:
            where = [FILTER, "m.id > ?"]
            params: List[Any] = [last_id]
            if args.max_id is not None:
                where.append("m.id <= ?"); params.append(args.max_id)
            sql = ("SELECT m.id, m.session_id, m.role, m.content, m.timestamp, m.token_count, "
                   "COALESCE(s.title,'untitled') AS title "
                   "FROM messages m LEFT JOIN sessions s ON m.session_id = s.id "
                   "WHERE " + " AND ".join(where) + " ORDER BY m.id LIMIT ?")
            params.append(rows_per_batch)
            batch = state_con.execute(sql, params).fetchall()
            if not batch:
                break
            payload: List[tuple] = []
            for r in batch:
                last_id = r["id"]
                seen += 1
                key = (r["session_id"], r["id"])
                if key in existing_keys:
                    continue
                content = r["content"]
                if len(content) > MAX_CONTENT:
                    content = content[:MAX_CONTENT] + TRUNC_SUFFIX
                payload.append((r["session_id"], r["id"], r["role"], content, r["title"],
                                NEW_SOURCE, r["timestamp"], int(r["token_count"] or 0)))
                existing_keys.add(key)
            if not payload:
                continue
            if args.dry_run:
                inserted += len(payload)
                continue
            with memos:  # one transaction per batch + invariant assertion
                memos.executemany(
                    "INSERT INTO memos_body(session_id, message_id, role, content, session_title, "
                    "source, created_at, token_count) VALUES (?,?,?,?,?,?,?,?)", payload)
                d = count_sources(memos, "dsh:%")
                o = count_sources(memos, "ops:%")
                if d != dsh_before or o != ops_before:
                    raise RuntimeError(f"INVARIANT VIOLATED in batch: dsh {dsh_before}->{d}, ops {ops_before}->{o}")
                inserted += len(payload)
            if seen % (rows_per_batch * 4) < rows_per_batch or len(batch) < rows_per_batch:
                print(f"  progress: scanned={seen} inserted={inserted} last_id={last_id}")

        summary["scanned"] = seen
        summary["inserted"] = inserted
        summary["last_message_id"] = last_id

        # 4) finalize
        if not args.dry_run:
            with memos:
                memos.execute("INSERT INTO memos_fts(memos_fts) VALUES('rebuild')")
                state.update({
                    "source": NEW_SOURCE,
                    "inserted_rows": int(state.get("inserted_rows", 0)) + inserted,
                    "last_message_id": last_id,
                    "since_id": args.since_id,
                    "max_id": args.max_id,
                    "last_run_at": datetime.now().isoformat(timespec="seconds"),
                })
                meta_set(memos, STATE_KEY, json.dumps(state, ensure_ascii=False))
            _snap, summary["snapshot_sha256_after"] = snapshot_sha(memos, MEMOS_DB, "after")
        summary["sha256_file_after"] = None if args.dry_run else sha256_file(MEMOS_DB)

        # 5) post assertions
        st_after = collect_stats(state_con, memos, args.since_id, args.max_id)
        summary["after"] = st_after
        summary["invariant_ok"] = (st_after["dsh_rows"] == dsh_before and st_after["ops_rows"] == ops_before)
        summary["body_equals_fts"] = (st_after["body_rows"] == st_after["fts_rows"])
        summary["elapsed_sec"] = round(time.time() - t0, 2)

        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(f"inserted={inserted}  legacy_retagged={retagged}  scanned={seen}")
            print(f"hermes:mybot now={st_after['new_source_existing']}  hermes:mybot@legacy now={st_after['legacy_rows']}")
            print(f"dsh:%={st_after['dsh_rows']} (was {dsh_before})  ops:%={st_after['ops_rows']} (was {ops_before})"
                  f"  invariant={'OK' if summary['invariant_ok'] else 'BROKEN'}")
            print(f"body={st_after['body_rows']} fts={st_after['fts_rows']} equal={summary['body_equals_fts']}")
            print(f"elapsed={summary['elapsed_sec']}s")
        return 0
    finally:
        state_con.close()
        memos.close()


def _print_stats(s: dict, db: Path) -> None:
    print(f"db={db}")
    print(f"eligible (filter) = {s['eligible']}  by_role={json.dumps(s['by_role'], ensure_ascii=False)}")
    print(f"user rows = {s['user_total']}  suspected system-injection = {s['suspect_injection_total']} "
          f"{json.dumps(s['suspect_injection'], ensure_ascii=False)}")
    print(f"state ts range = {s['state_ts_min']} .. {s['state_ts_max']}")
    print(f"existing hermes:mybot = {s['new_source_existing']} id_range={s['new_source_id_range']}")
    print(f"existing hermes:mybot@legacy = {s['legacy_rows']} id_range={s['legacy_id_range']}")
    print(f"dsh:% = {s['dsh_rows']}  ops:% = {s['ops_rows']}")
    print(f"memos_body = {s['body_rows']}  memos_fts = {s['fts_rows']}")


if __name__ == "__main__":
    raise SystemExit(main())