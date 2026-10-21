#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""queue_cursor_check.py — 判定「CLI /queue 批次里哪些条目真的执行了」

为什么需要它（机理）:
  CLI 的 /queue 是【进程内 queue.Queue()】，不落盘；进程一死整批消失。
  `.hermes_history` 只证明「键入了」，只有 state.db 里 role='user' 的回合才算「执行了」。
  所以恢复队列时，唯一可靠的定界办法是【FIFO 游标法】：
    解析 .hermes_history 的 /q|/queue 行 → 按时间分批 → 逐条去 state.db 找 user 回合。

用法:
  python queue_cursor_check.py --profile mybot                 # 最近 3 个批次
  python queue_cursor_check.py --profile mybot --last-batches 5
  python queue_cursor_check.py --profile mybot --json out.json

输出: 每批次的 executed / pending 清单（pending 条目需人工/看板补做）。
退出码: 0=有 pending（需处理）  2=全部已执行  3=参数/文件错误

依赖: 只用标准库。只读打开 state.db（file:...?mode=ro）。
"""
import argparse, datetime, io, json, os, re, sqlite3, sys

TS_RE = re.compile(r"^# (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)")
Q_RE = re.compile(r"^\+?/q(ueue)?(\s|$)")


def parse_history(path):
    """把 .hermes_history 解析成 [(ts, 'queue'|'other', prompt)]。
    ⚠️ 坑1: 每行行首都有 '+'（命令与续行都是），不能用 '+' 判续行。
    ⚠️ 坑2: '# <ISO 时间戳>' 是分组行，必须先 flush 上一条再起新条目。"""
    items, ts, cmd, buf = [], None, None, []

    def flush():
        nonlocal cmd, buf
        if cmd is not None:
            items.append((ts, cmd, "\n".join(buf).strip()))
        cmd, buf = None, []

    with io.open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            m = TS_RE.match(line)
            if m:
                flush()
                ts = m.group(1)
                continue
            body = line[1:] if line.startswith("+") else line
            if Q_RE.match(body):
                flush()
                cmd = "queue"
                buf = [Q_RE.sub("", body).strip()]
            elif cmd is not None:
                buf.append(body)
    flush()
    return items


def batch_up(items, gap_seconds=5400):
    """时间相邻（默认 90 分钟）的连续 /queue 条目算同一批。"""
    q = [it for it in items if it[1] == "queue"]
    out = []
    for it in q:
        if out:
            t0 = datetime.datetime.strptime(out[-1][-1][0][:19], "%Y-%m-%d %H:%M:%S")
            t1 = datetime.datetime.strptime(it[0][:19], "%Y-%m-%d %H:%M:%S")
            if (t1 - t0).total_seconds() <= gap_seconds:
                out[-1].append(it)
                continue
        out.append([it])
    return out


def norm(s):
    return re.sub(r"[\s\*_`#>\-]+", "", s or "").strip().lower()


def fetch_user_turns(db, span=30000):
    """只读打开 state.db；用 rowid 区间取 user 回合（避免全表 LIKE 扫描）。"""
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=60)
    mx = con.execute("select max(rowid) from messages").fetchone()[0]
    lo = max(1, mx - span)
    rows = list(con.execute(
        "select rowid, timestamp, session_id, substr(content,1,400) from messages "
        "where rowid>=? and role='user' order by rowid", (lo,)))
    return con, [(r[0], float(r[1]), r[2], r[3] or "") for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="mybot")
    ap.add_argument("--home", default="D:/hermes/hermes-data/profiles")
    ap.add_argument("--last-batches", type=int, default=3)
    ap.add_argument("--span", type=int, default=30000, help="回看多少个 rowid")
    ap.add_argument("--json")
    a = ap.parse_args()

    base = os.path.join(a.home, a.profile)
    hist, db = os.path.join(base, ".hermes_history"), os.path.join(base, "state.db")
    for p in (hist, db):
        if not os.path.exists(p):
            print("MISSING: " + p)
            return 3

    items = parse_history(hist)
    batches = batch_up(items)[-a.last_batches:]
    con, turns = fetch_user_turns(db, a.span)
    print("profile=%s | /queue 条目=%d | 批次数=%d | 取到 user 回合=%d (rowid %s..%s)"
          % (a.profile, len([i for i in items if i[1] == "queue"]), len(batches),
             len(turns), turns[0][0] if turns else "-", turns[-1][0] if turns else "-"))

    def iso(t):
        return datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")

    result = {"profile": a.profile, "batches": [], "executed": 0, "pending": 0}
    for bi, b in enumerate(batches):
        rec = {"first": b[0][0], "last": b[-1][0], "n": len(b), "executed": [], "pending": []}
        print("\n===== batch: %s -> %s  (n=%d) =====" % (b[0][0], b[-1][0], len(b)))
        for ts, _, prompt in b:
            t0 = datetime.datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S").timestamp()
            k1, k2 = norm(prompt), norm(prompt)[:20]
            hit = [t for t in turns if t0 - 90 <= t[1] <= t0 + 6 * 3600 and k1[:40] and k1[:40] in norm(t[3])]
            if not hit:
                hit = [t for t in turns if t0 - 90 <= t[1] <= t0 + 6 * 3600 and len(k2) >= 8 and k2 in norm(t[3])]
            if hit:
                r = hit[0]
                print("  ✔ EXECUTED [%s] %s" % (ts, prompt.replace("\n", " ")[:78]))
                print("        -> %s @ %s" % (r[2], iso(r[1])))
                rec["executed"].append({"ts": ts, "prompt": prompt, "hit_session": r[2], "hit_ts": iso(r[1])})
                result["executed"] += 1
            else:
                print("  ✗ PENDING  [%s] %s" % (ts, prompt.replace("\n", " ")[:150]))
                rec["pending"].append({"ts": ts, "prompt": prompt})
                result["pending"] += 1
        result["batches"].append(rec)

    print("\n===== SUMMARY: executed=%d  pending=%d =====" % (result["executed"], result["pending"]))
    if a.json:
        io.open(a.json, "w", encoding="utf-8").write(json.dumps(result, ensure_ascii=False, indent=1))
        print("wrote " + a.json)
    return 0 if result["pending"] else 2


if __name__ == "__main__":
    sys.exit(main())
