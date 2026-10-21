#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""task_dispatch_mcp.py -- single-file stdio MCP server: cross-executor task dispatcher.

Routes a task to DSH (local coding harness) / Hermes (messaging+memory+kanban agent) /
both / durable (Hermes kanban queue), then executes it. Hermes components (memory,
message channels, kanban, toolsets) can be attached to any dispatch.

Transport: MCP 2024-11-05 over stdio, newline-delimited JSON-RPC 2.0.
stdout carries ONLY one JSON-RPC frame per line; all logging goes to stderr.

Launch (pure argv, no shell):
  "C:\\Users\\Administrator\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\python.exe"
  -u "D:\\hermes\\hermes-data\\profiles\\mybot\\scripts\\task_dispatch_mcp.py"

Safety: read-only on Hermes DBs (mode=ro + PRAGMA query_only=ON); no writes to any
Hermes .db; never auto-sends a message unless dispatch_task is called with a real
notify_channel and dry_run=false.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "task-dispatch"
SERVER_VERSION = "1.0.0"

TZ8 = timezone(timedelta(hours=8))

DSH_CLI = os.environ.get("TASK_DISPATCH_DSH_CLI") or \
    r"D:\Users\Administrator\AppData\Local\Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd"
HERMES_CLI = os.environ.get("TASK_DISPATCH_HERMES_CLI") or r"D:\hermes\hermes-data\bin\hermes.exe"
DSH_EXE = os.environ.get("TASK_DISPATCH_DSH_EXE") or \
    r"D:\Users\Administrator\AppData\Local\Programs\DeepSeek Harness\DeepSeek Harness.exe"
DSH_CLI_JS = os.environ.get("TASK_DISPATCH_DSH_CLI_JS") or \
    r"D:\Users\Administrator\AppData\Local\Programs\DeepSeek Harness\resources\app.asar\dsh\node_modules\@deepseek-ai\dsh-desktop-host\lib\cli.js"
HERMES_HOME = Path(os.environ.get("HERMES_HOME") or r"D:\hermes\hermes-data\profiles\mybot")
PROFILES_DIR = HERMES_HOME.parent
HERMES_DATA = HERMES_HOME.parents[1]
KANBAN_DB = Path(os.environ.get("TASK_DISPATCH_KANBAN_DB") or (HERMES_DATA / "kanban.db"))
MEMOS_DB = Path(os.environ.get("TASK_DISPATCH_MEMOS_DB") or (HERMES_HOME / "knowledge_base" / "memos_vec.db"))
CHANNEL_DIR = HERMES_DATA / "channel_directory.json"
LEDGER = Path(os.environ.get("TASK_DISPATCH_LEDGER") or (HERMES_HOME / "ops" / "dispatch_ledger.jsonl"))

KNOWN_PROFILES = ["mybot", "qqbot3", "qqbot4", "qqbot5", "dong", "linshuo", "wenming", "default"]
DEFAULT_PROFILE = "mybot"

MAX_OUTPUT_HEAD = 2000
MEMORY_SOURCES = ("hermes:mybot", "dsh:")

log = logging.getLogger("task-dispatch")
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("[task-dispatch] %(levelname)s %(message)s"))
    log.addHandler(_h)
log.setLevel(logging.INFO)
log.propagate = False


class ToolError(Exception):
    def __init__(self, message: str, code: str = "dispatch_error") -> None:
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------- routing

# id -> (target, weight, regex, human)
ROUTE_RULES: list[tuple[str, str, int, str, str]] = [
    ("R_MSG_PLATFORM", "hermes", 5,
     r"feishu|飞书|dingtalk|钉钉|weixin|微信|wechat|qqbot|telegram|discord|slack|whatsapp|signal|消息平台|群发|群里|频道|channel",
     "涉及消息平台/IM 通道"),
    ("R_NOTIFY", "hermes", 4,
     r"通知|提醒|告知|回复|发给|发送|发一条|推送给|播报|通报|notify|send\b|push\b|deliver",
     "需要对外通知/交付"),
    ("R_KANBAN_ADMIN", "hermes", 4,
     r"kanban|看板|cron|定时任务|排程|schedule|skill|技能|插件|plugin|toolset|工具集|工作流|workflow",
     "涉及 Hermes 看板/cron/skill/插件管理"),
    ("R_OPS_COST", "hermes", 4,
     r"用量|成本|花费|烧了|token\s*消耗|最贵|账单|usage\b|cost\b|spend\b|budget|运营台账",
     "查询用量/成本/运营台账"),
    ("R_MEMORY_CTX", "hermes", 2,
     r"记忆|历史|经验|知识库|memory|recall|memos|注入|检索历史",
     "需要 Hermes 记忆/知识库组件"),
    ("R_REPO_CODE", "dsh", 5,
     r"仓库|repo\b|代码|重构|refactor|修好|修复|fix\b|bug|测试|test|单测|编译|build|commit|提交|pull request|\bpr\b|合并|模块|函数|接口|实现|auth|依赖",
     "涉及仓库代码/测试/重构"),
    ("R_FS", "dsh", 3,
     r"文件系统|目录|文件|落盘|读取|写入|脚本|script|遍历",
     "涉及文件系统操作"),
    ("R_LONG_AUTONOMOUS", "dsh", 3,
     r"自主|端到端|长时间|从头到尾|完整实现|autonomous|overnight",
     "长时间自主编码"),
    ("R_DURABLE", "durable", 6,
     r"持续|长期|三天|几天|多天|后台|异步|队列|重试|audit|审计|watch\b|监控|轮询|跟踪.{0,6}(天|周)|durable|daemon",
     "长任务/需重试/需审计链"),
]
COMPILED = [(rid, tgt, w, re.compile(pat, re.IGNORECASE | re.UNICODE), human)
            for rid, tgt, w, pat, human in ROUTE_RULES]

RESEARCH_RE = re.compile(r"论文|paper|arxiv|调研|研究|搜索|web\b|benchmark|文献", re.IGNORECASE)


def _score_task(task: str) -> tuple[dict[str, float], list[str]]:
    scores = {"dsh": 0.0, "hermes": 0.0, "durable": 0.0}
    matched: list[str] = []
    for rid, tgt, w, rx, _human in COMPILED:
        if rx.search(task or ""):
            scores[tgt] += w
            matched.append(rid)
    return scores, matched


def _channels() -> list[dict]:
    """Available messaging targets (read-only). Prefers `hermes send --list --json`
    (canonical platform:id), then channel_directory.json, then plain-text parsing."""
    if _CHANNELS_CACHE is not None:
        return _CHANNELS_CACHE
    out: list[dict] = []
    # 1) structured CLI
    try:
        r = subprocess.run(_exec_argv(HERMES_CLI, ["send", "--list", "--json"]), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=30)
        data = json.loads(r.stdout or "{}")
        for platform, items in (data.get("platforms") or {}).items():
            for it in items or []:
                cid = it.get("id")
                if not cid:
                    continue
                out.append({"platform": platform, "target": f"{platform}:{cid}",
                            "name": it.get("name", ""), "chat_type": it.get("type", "")})
    except Exception as exc:
        log.warning("`hermes send --list --json` failed: %s", exc)
    # 2) channel directory file
    if not out:
        try:
            if CHANNEL_DIR.exists():
                data = json.loads(CHANNEL_DIR.read_text(encoding="utf-8"))
                for platform, items in (data.get("platforms") or {}).items():
                    for it in items or []:
                        cid = it.get("id") or it.get("chat_id")
                        if cid:
                            out.append({"platform": platform, "target": f"{platform}:{cid}",
                                        "name": it.get("name", ""), "chat_type": it.get("type", "")})
        except Exception as exc:
            log.warning("channel_directory read failed: %s", exc)
    # 3) plain-text fallback
    if not out:
        try:
            r = subprocess.run(_exec_argv(HERMES_CLI, ["send", "--list"]), capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=30)
            for line in (r.stdout or "").splitlines():
                m = re.match(r"^\s{2}([a-z0-9_]+:[^\s(]+)", line, re.IGNORECASE)
                if m:
                    tgt = m.group(1).rstrip(")")
                    out.append({"platform": tgt.split(":", 1)[0], "target": tgt, "name": ""})
        except Exception as exc:
            log.warning("`hermes send --list` failed: %s", exc)
    globals()["_CHANNELS_CACHE"] = out
    return out


def route_task(task: str, prefer: str = "auto", constraints: dict | None = None) -> dict:
    constraints = constraints or {}
    scores, matched = _score_task(task)
    flags: list[str] = []

    if constraints.get("must_notify"):
        scores["hermes"] += 4
        flags.append("constraint:must_notify(+hermes)")
    if constraints.get("no_network"):
        flags.append("constraint:no_network(→本地 dsh 优先)")
    if constraints.get("cheap"):
        flags.append("constraint:cheap(→避免长任务)")
    if constraints.get("prefer_durable"):
        scores["durable"] += 6
        flags.append("constraint:prefer_durable")

    prefer = (prefer or "auto").lower()
    if prefer != "auto":
        target = prefer
        rules = ["R_PREFER"]
        rationale = f"调用方显式 prefer={prefer}。" + (f" 同时命中：{', '.join(matched)}。" if matched else "")
        confidence = 0.99
    elif scores["durable"] > 0:
        target = "durable"
        rules = [m for m in matched if m == "R_DURABLE"] or ["R_DURABLE"]
        rationale = ("任务具备长周期/重试/审计特征，应走 Hermes kanban durable 队列而不是同步执行。"
                     if matched else "constraints 要求 durable。")
        confidence = 0.9
    elif scores["dsh"] > 0 and scores["hermes"] > 0:
        target = "both"
        rules = matched
        rationale = ("既有本地代码/文件系统工作量，又需要 Hermes 的对外交付或记忆组件："
                     "由 dsh 执行 + Hermes 组件协助（记忆注入 / 结果通知）。")
        confidence = 0.85
    elif scores["hermes"] > scores["dsh"] and scores["hermes"] > 0:
        target = "hermes"
        rules = [m for m in matched if m.startswith("R_MSG") or m.startswith("R_NOTIFY")
                 or m.startswith("R_KANBAN") or m.startswith("R_OPS") or m.startswith("R_PROFILE")
                 or m.startswith("R_MEMORY")]
        rationale = "任务主要是消息平台/通知/看板/记忆等 Hermes 组件能力，交给 Hermes 执行。"
        confidence = min(0.95, 0.6 + 0.05 * len(rules))
    elif scores["dsh"] > 0:
        target = "dsh"
        rules = [m for m in matched if m.startswith("R_REPO") or m.startswith("R_FS") or m.startswith("R_LONG")]
        rationale = "任务是仓库代码/文件系统/自主编码工作，交给本地 DSH 执行最合适。"
        confidence = min(0.95, 0.6 + 0.05 * len(rules))
    else:
        target = "dsh"
        rules = ["R_DEFAULT"]
        rationale = "未命中任何专有规则；默认交给本地 DSH（最通用、单次调用成本最低）。"
        confidence = 0.35

    if constraints.get("no_network") and target == "hermes":
        rationale += " 但 no_network 约束下需确认 Hermes 侧无需外网。"
        confidence = max(0.3, confidence - 0.2)

    # suggested components (concrete)
    comps: dict[str, Any] = {}
    wants_memory = bool(re.search(r"记忆|历史|经验|知识库|memory|recall|注入", task, re.I)) or target in ("hermes", "both", "durable")
    if wants_memory:
        comps["memory"] = {"enabled": True, "k": 5, "sources": list(MEMORY_SOURCES)}
    wants_notify = bool(re.search(r"通知|提醒|发送|发给|回复|群发|播报|通报|notify|send", task, re.I)) \
        or bool(constraints.get("must_notify")) or target in ("hermes", "both")
    if wants_notify:
        chans = _channels()
        comps["notify"] = {"channel": (chans[0]["target"] if chans else None), "on": "finish",
                           "transport": "hermes send --to"}
    if RESEARCH_RE.search(task):
        comps["toolsets"] = ["web"]
    if target == "durable":
        comps["kanban"] = {"assignee": DEFAULT_PROFILE, "wait": False, "cli": "hermes kanban create"}
    if target in ("dsh", "both"):
        comps["executor"] = {"cli": "dsh", "profile": "headless", "workspace": constraints.get("workspace", "cwd")}

    alts = []
    for alt in ("dsh", "hermes", "both", "durable"):
        if alt != target:
            alts.append({"target": alt,
                         "why": {"dsh": "若希望本地一次性编码执行",
                                 "hermes": "若希望交给 Hermes agent（消息/记忆/看板）",
                                 "both": "若要 dsh 执行 + Hermes 组件协助",
                                 "durable": "若任务长/需重试审计，走 kanban 队列"}[alt]})
    result = {"target": target, "confidence": round(confidence, 3), "rationale": rationale,
              "rules": rules, "matched_rules": matched, "scores": scores,
              "constraint_flags": flags, "suggested_components": comps, "alternatives": alts}
    return result


# ------------------------------------------------------------------ execution

def _exec_argv(cli: str, args: list[str]) -> list[str]:
    if cli.lower().endswith((".cmd", ".bat")):
        return ["cmd.exe", "/d", "/c", cli, *args]
    return [cli, *args]


def _dsh_argv(args: list[str]) -> tuple[list[str], dict | None]:
    """Run dsh by its real target (Electron exe + cli.js with ELECTRON_RUN_AS_NODE=1).

    Invoking the .cmd launcher through `cmd /c` breaks on the install path's spaces;
    calling the exe directly is what dsh.cmd does and is robust for arbitrary prompts.
    Falls back to the .cmd launcher when the exe/cli.js are absent.
    """
    # NOTE: DSH_CLI_JS lives INSIDE app.asar, so it is not a real file on disk;
    #       only the Electron exe can be existence-checked.
    if Path(DSH_EXE).exists():
        return [DSH_EXE, "--expose-internals", DSH_CLI_JS, *args], {"ELECTRON_RUN_AS_NODE": "1"}
    return _exec_argv(DSH_CLI, args), None


def _run(argv: list[str], cwd: str | None, timeout: int, env: dict | None = None) -> dict:
    t0 = time.time()
    run_env = None
    if env:
        run_env = dict(os.environ)
        run_env.update(env)
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, env=run_env)
        return {"exit_code": proc.returncode, "stdout": proc.stdout or "", "stderr": proc.stderr or "",
                "duration": round(time.time() - t0, 2), "timed_out": False}
    except subprocess.TimeoutExpired as exc:
        return {"exit_code": 124, "stdout": (exc.stdout or "") if isinstance(exc.stdout, str) else "",
                "stderr": f"TIMEOUT after {timeout}s", "duration": round(time.time() - t0, 2), "timed_out": True}
    except Exception as exc:
        return {"exit_code": 127, "stdout": "", "stderr": f"exec failed: {exc}",
                "duration": round(time.time() - t0, 2), "timed_out": False}


# ------------------------------------------------------------- memory injection

def _memos_connect() -> sqlite3.Connection:
    uri = "file:" + str(MEMOS_DB).replace("\\", "/") + "?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        return con
    except sqlite3.Error as exc:
        log.warning("read-only URI failed (%s); fallback query_only", exc)
        con = sqlite3.connect(str(MEMOS_DB), timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        return con


def search_memory(task: str, k: int = 5) -> list[dict]:
    tokens = re.findall(r"[\w\u4e00-\u9fff]{2,}", task or "")[:12]
    if not tokens:
        return []
    match_q = " OR ".join(f'"{t}"' for t in tokens)
    rows: list[dict] = []
    con = _memos_connect()
    try:
        src_clause = " OR ".join(["b.source=?"] + ["b.source LIKE ?"] * (len(MEMORY_SOURCES) - 1))
        params = ["hermes:mybot", *[s + "%" for s in MEMORY_SOURCES[1:]]]
        try:
            rows = [dict(r) for r in con.execute(
                "SELECT b.rowid, b.source, b.session_id, b.role, b.session_title, b.content, f.rank "
                "FROM memos_fts f JOIN memos_body b ON f.rowid=b.rowid "
                f"WHERE memos_fts MATCH ? AND ({src_clause}) ORDER BY f.rank LIMIT ?",
                (match_q, *params, k))]
        except sqlite3.Error as exc:
            log.warning("FTS MATCH failed (%s); LIKE fallback", exc)
        if not rows:
            like = " OR ".join(["b.content LIKE ?"] * min(len(tokens), 5))
            lp = [f"%{t}%" for t in tokens[:5]]
            rows = [dict(r) for r in con.execute(
                "SELECT b.rowid, b.source, b.session_id, b.role, b.session_title, b.content, NULL AS rank "
                "FROM memos_body b "
                f"WHERE ({src_clause}) AND ({like}) LIMIT ?",
                (*params, *lp, k))]
    finally:
        con.close()
    out = []
    for r in rows:
        rank = r.get("rank")
        score = round(1.0 / (1.0 + abs(float(rank))), 4) if rank is not None else 0.5
        out.append({"rowid": r["rowid"], "source": r["source"], "role": r["role"],
                    "session_title": r["session_title"], "score": score,
                    "snippet": (r["content"] or "").replace("\n", " ")[:220]})
    return out


def build_memory_block(hits: list[dict]) -> str:
    if not hits:
        return ""
    lines = ["## 相关历史/经验"]
    for h in hits:
        lines.append(f"- [{h['source']}#{h['rowid']}] {h['snippet']}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- notifications

def _notify_argv(channel: str, text: str) -> list[str]:
    return _exec_argv(HERMES_CLI, ["send", "--to", channel, text])


def _ledger_append(entry: dict) -> None:
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.warning("ledger append failed: %s", exc)


def _iso_now() -> str:
    return datetime.now(TZ8).isoformat(timespec="seconds")


# --------------------------------------------------------------------- tool impl

def t_route_task(args: dict) -> dict:
    task = str(args.get("task") or "").strip()
    if not task:
        raise ToolError("task is required", "bad_request")
    return route_task(task, str(args.get("prefer") or "auto"), args.get("constraints") or {})


def _dispatch_id() -> str:
    return "disp-" + datetime.now(TZ8).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]


def t_dispatch_task(args: dict) -> dict:
    task = str(args.get("task") or "").strip()
    if not task:
        raise ToolError("task is required", "bad_request")
    target = str(args.get("target") or "auto").lower()
    profile = str(args.get("profile") or DEFAULT_PROFILE)
    workspace = args.get("workspace")
    toolsets = args.get("toolsets")
    notify_channel = args.get("notify_channel") or None
    notify_on = str(args.get("notify_on") or "finish").lower()
    inject_memory = bool(args.get("inject_memory"))
    memory_k = int(args.get("memory_k") or 5)
    durable = bool(args.get("durable"))
    timeout_seconds = int(args.get("timeout_seconds") or 900)
    dry_run = bool(args.get("dry_run"))
    dispatch_id = _dispatch_id()

    decision = route_task(task, "auto", {})
    if target == "auto":
        target = decision["target"]
    else:
        decision = {**decision, "target": target, "override": True}
    if durable and target != "durable":
        target = "durable"
        decision = {**decision, "target": "durable", "override": "durable=true"}
    if target == "both":
        inject_memory = inject_memory or True
        if notify_on == "finish":
            notify_on = "finish"

    # context assembly (memory injection)
    injected: list[dict] = []
    prompt = task
    if inject_memory:
        injected = search_memory(task, memory_k)
        prompt = build_memory_block(injected) + "## 任务\n" + task

    result: dict[str, Any] = {
        "dispatch_id": dispatch_id, "task": task, "target": target, "decision": decision,
        "profile": profile, "workspace": workspace, "injected_memory": injected,
        "dry_run": dry_run, "notified": [], "prompt_head": prompt[:500],
    }

    kanban_task_id = None
    notif_start = None
    if notify_channel and notify_on in ("start", "both"):
        notif_start = _notify_argv(notify_channel, f"[{dispatch_id}] 任务开始：{task[:180]}")

    # ---------------- durable ----------------
    if target == "durable":
        title = task.splitlines()[0][:80] if task.splitlines() else task[:80]
        # NOTE: the real CLI takes title POSITIONALLY (not --title); verified against hermes v0.21.7.
        argv = _exec_argv(HERMES_CLI, ["kanban", "create", title, "--assignee", profile,
                                       "--body-file", "-", "--json"])
        result["argv"] = argv
        if dry_run:
            result["status"] = "dry_run"
            result["will_send"] = {"start": notif_start}
            result["body_head"] = prompt[:500]
            return result
        t0 = time.time()
        try:
            proc = subprocess.run(argv, input=prompt, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=120)
            out = (proc.stdout or "").strip()
            if not out:
                out = (proc.stderr or "").strip()
            try:
                j = json.loads(out)
                kanban_task_id = j.get("task_id") or j.get("id") or j.get("task", {}).get("id")
            except Exception:
                m = re.search(r"(t_[0-9a-f]{8})", out)
                kanban_task_id = m.group(1) if m else None
            exit_code, out_head = proc.returncode, out[:MAX_OUTPUT_HEAD]
        except subprocess.TimeoutExpired:
            exit_code, out_head = 124, "TIMEOUT creating kanban task"
        except Exception as exc:
            exit_code, out_head = 127, f"exec failed: {exc}"
        result.update({"kanban_task_id": kanban_task_id, "exit_code": exit_code,
                       "output_head": out_head, "duration": round(time.time() - t0, 2)})
        if notify_channel and notify_on in ("finish", "both") and exit_code == 0:
            nargv = _notify_argv(notify_channel,
                                 f"[{dispatch_id}] 已入队 kanban 任务 {kanban_task_id}：{task[:180]}")
            nr = _run(nargv, None, 60)
            result["notified"].append({"on": "finish", "argv": nargv, "exit_code": nr["exit_code"]})
        _ledger_append({"ts": _iso_now(), "dispatch_id": dispatch_id, "task": task, "target": target,
                        "decision": decision, "argv": argv, "exit_code": exit_code,
                        "duration": result["duration"], "output_head": out_head,
                        "injected_memory": injected, "notified": result["notified"]})
        return result

    # ---------------- dsh / hermes / both ----------------
    run_cwd = workspace if workspace else None
    run_env = None
    if target in ("dsh", "both"):
        argv, run_env = _dsh_argv(["--profile", "headless", prompt])
    else:
        hargs = ["-z", prompt, "--yolo", "--cli"]
        if toolsets:
            hargs += ["-t", str(toolsets)]
        if workspace:
            hargs += ["--in", str(workspace)]
        argv = _exec_argv(HERMES_CLI, hargs)
    result["argv"] = argv

    if dry_run:
        result["status"] = "dry_run"
        result["will_send"] = {"start": notif_start,
                               "finish": _notify_argv(notify_channel, f"[{dispatch_id}] 结果：<output_head>")
                               if notify_channel else None}
        return result

    notified: list[dict] = []
    if notif_start:
        nr = _run(notif_start, None, 60)
        notified.append({"on": "start", "argv": notif_start, "exit_code": nr["exit_code"]})

    run = _run(argv, run_cwd, timeout_seconds, run_env)
    exit_code = run["exit_code"]
    output_head = (run["stdout"] or run["stderr"])[:MAX_OUTPUT_HEAD]
    result.update({"exit_code": exit_code, "stdout_head": run["stdout"][:MAX_OUTPUT_HEAD],
                   "stderr_head": run["stderr"][:MAX_OUTPUT_HEAD], "output_head": output_head,
                   "duration": run["duration"], "timed_out": run["timed_out"]})

    if notify_channel and notify_on in ("finish", "both"):
        summary = f"[{dispatch_id}] target={target} exit={exit_code}\n{(run['stdout'] or '').strip()[:1200]}"
        nargv = _notify_argv(notify_channel, summary)
        nr = _run(nargv, None, 60)
        notified.append({"on": "finish", "argv": nargv, "exit_code": nr["exit_code"]})
    result["notified"] = notified

    _ledger_append({"ts": _iso_now(), "dispatch_id": dispatch_id, "task": task, "target": target,
                    "decision": decision, "argv": argv, "exit_code": exit_code,
                    "duration": run["duration"], "output_head": output_head,
                    "injected_memory": injected, "notified": notified})
    return result


def t_task_status(args: dict) -> dict:
    dispatch_id = args.get("dispatch_id")
    limit = int(args.get("limit") or 10)
    if not LEDGER.exists():
        return {"ledger": str(LEDGER), "count": 0, "entries": []}
    entries = []
    with LEDGER.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if dispatch_id and e.get("dispatch_id") != dispatch_id:
                continue
            entries.append(e)
    result = {"ledger": str(LEDGER), "total_lines": len(entries), "returned": len(entries[-limit:]),
              "entries": entries[-limit:]}
    if dispatch_id:
        result["found"] = any(e.get("dispatch_id") == dispatch_id for e in entries)
    return result


_VER_CACHE: dict[str, str] = {}
_CHANNELS_CACHE: list[dict] | None = None


def _version(cli: str, args: list[str]) -> str:
    if cli in _VER_CACHE:
        return _VER_CACHE[cli]
    r = _run(_exec_argv(cli, args), None, 120)
    v = (r["stdout"] or r["stderr"]).strip().splitlines()[0] if (r["stdout"] or r["stderr"]).strip() else "unknown"
    _VER_CACHE[cli] = v
    return v


def _version_dsh() -> str:
    if DSH_CLI in _VER_CACHE:
        return _VER_CACHE[DSH_CLI]
    argv, env = _dsh_argv(["--version"])
    r = _run(argv, None, 120, env)
    out = (r["stdout"] or r["stderr"]).strip().splitlines()
    v = out[0] if out else "unknown"
    _VER_CACHE[DSH_CLI] = v
    return v


def t_list_executors(_args: dict) -> dict:
    profiles = []
    try:
        for d in sorted(PROFILES_DIR.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                profiles.append({"name": d.name, "has_config": (d / "config.yaml").exists()})
    except Exception as exc:
        log.warning("profiles scan failed: %s", exc)

    channels = _channels()
    mem = {"db": str(MEMOS_DB), "rows": None, "by_source": []}
    try:
        con = _memos_connect()
        try:
            mem["rows"] = con.execute("SELECT COUNT(*) FROM memos_body").fetchone()[0]
            mem["by_source"] = [{"source": r[0], "rows": r[1]} for r in con.execute(
                "SELECT source, COUNT(*) FROM memos_body GROUP BY source ORDER BY 2 DESC LIMIT 10")]
        finally:
            con.close()
    except Exception as exc:
        mem["error"] = str(exc)

    kanban = {"db": str(KANBAN_DB), "tasks": None, "by_status": []}
    try:
        uri = "file:" + str(KANBAN_DB).replace("\\", "/") + "?mode=ro"
        k = sqlite3.connect(uri, uri=True, timeout=15)
        k.execute("PRAGMA query_only=ON")
        kanban["tasks"] = k.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        kanban["by_status"] = [{"status": r[0], "count": r[1]}
                               for r in k.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")]
        k.close()
    except Exception as exc:
        kanban["error"] = str(exc)

    return {
        "executors": {
            "dsh": {"cli": DSH_CLI, "exe": DSH_EXE, "cli_js": DSH_CLI_JS,
                     "version": _version_dsh(), "invoke": 'dsh --profile headless "<task>"',
                     "kind": "local coding harness"},
            "hermes": {"cli": HERMES_CLI, "version": _version(HERMES_CLI, ["--version"]),
                       "invoke": 'hermes -z "<prompt>" --yolo --cli', "kind": "messaging/memory/kanban agent"},
        },
        "profiles": profiles,
        "messaging_channels": channels,
        "memory": mem,
        "kanban": kanban,
        "ledger": str(LEDGER),
    }


# ------------------------------------------------------------------ MCP server

TOOLS = [
    {"name": "route_task",
     "description": ("Decide where a task should run: dsh (local coding harness) / hermes "
                     "(messaging+memory+kanban agent) / both (dsh executes, Hermes components assist) / "
                     "durable (Hermes kanban queue). Pure decision, no side effects. Returns target, "
                     "confidence, rationale, matched rule ids and concrete suggested_components."),
     "inputSchema": {"type": "object", "properties": {
         "task": {"type": "string", "description": "Natural-language task."},
         "prefer": {"type": "string", "enum": ["auto", "dsh", "hermes", "both", "durable"], "default": "auto"},
         "constraints": {"type": "object", "properties": {
             "no_network": {"type": "boolean"}, "cheap": {"type": "boolean"},
             "must_notify": {"type": "boolean"}, "prefer_durable": {"type": "boolean"}},
             "additionalProperties": True}},
         "required": ["task"], "additionalProperties": False}},
    {"name": "dispatch_task",
     "description": ("Execute a task via dsh / hermes / both / durable (kanban). Optionally inject "
                     "MemOS memory, notify a channel via `hermes send`, and append a JSONL ledger row."),
     "inputSchema": {"type": "object", "properties": {
         "task": {"type": "string"},
         "target": {"type": "string", "enum": ["auto", "dsh", "hermes", "both", "durable"], "default": "auto"},
         "profile": {"type": "string"}, "workspace": {"type": "string"}, "toolsets": {"type": "string"},
         "notify_channel": {"type": "string"}, "notify_on": {"type": "string", "enum": ["start", "finish", "both"], "default": "finish"},
         "inject_memory": {"type": "boolean", "default": False}, "memory_k": {"type": "integer", "default": 5},
         "durable": {"type": "boolean", "default": False}, "timeout_seconds": {"type": "integer", "default": 900},
         "dry_run": {"type": "boolean", "default": False}},
         "required": ["task"], "additionalProperties": False}},
    {"name": "task_status",
     "description": "Read the dispatch ledger (ops/dispatch_ledger.jsonl); filter by dispatch_id or return the last N.",
     "inputSchema": {"type": "object", "properties": {
         "dispatch_id": {"type": "string"}, "limit": {"type": "integer", "default": 10}},
         "additionalProperties": False}},
    {"name": "list_executors",
     "description": "Read-only inventory: dsh/hermes CLI paths + versions, Hermes profiles, messaging channels, memory row counts, kanban task counts.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
]

_DISPATCH = {
    "route_task": t_route_task,
    "dispatch_task": t_dispatch_task,
    "task_status": t_task_status,
    "list_executors": t_list_executors,
}

INSTRUCTIONS = (
    "Cross-executor task dispatcher for DSH + Hermes. Use route_task to decide target "
    "(dsh/hermes/both/durable) with an explainable rationale; use dispatch_task to run it "
    "(dsh --profile headless, hermes -z ... --yolo --cli, or hermes kanban create). "
    "Hermes components can assist any dispatch: memory injection (inject_memory), messaging "
    "(notify_channel via `hermes send`), durable queue (durable=true). Use task_status to read "
    "the ledger and list_executors for a read-only inventory. Always prefer dry_run=true when "
    "testing notifications so no real message is sent."
)


def _jsonrpc_result(msg_id, result):
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _jsonrpc_error(msg_id, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": err}


def _tool_result(payload: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}], "isError": False}


def _tool_error(message: str, code: str) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(
        {"success": False, "error": message, "error_code": code}, ensure_ascii=False)}], "isError": True}


def _handle_tools_call(params):
    if not isinstance(params, dict):
        raise ToolError("params must be an object", "bad_request")
    name = params.get("name")
    if not isinstance(name, str) or name not in _DISPATCH:
        raise ToolError("unknown tool: %r" % (name,), "unknown_tool")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise ToolError("arguments must be an object", "bad_request")
    return _DISPATCH[name](arguments)


def handle_message(msg):
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
                return _jsonrpc_result(msg_id, _tool_result(_handle_tools_call(msg.get("params"))))
            except ToolError as exc:
                log.warning("tool call failed: %s", exc)
                return _jsonrpc_result(msg_id, _tool_error(str(exc), exc.code))
        if method.startswith("notifications/"):
            return None
        if not has_id:
            return None
        return _jsonrpc_error(msg_id, -32601, "Method not found: %s" % method)
    except Exception as exc:
        log.error("internal error on %s: %s\n%s", method, exc, traceback.format_exc())
        return _jsonrpc_error(msg_id, -32603, "Internal error: %s" % exc) if has_id else None


def _write_frame(obj) -> None:
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.buffer.write(data.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def main() -> int:
    log.info("started pid=%s dsh=%s hermes=%s ledger=%s", os.getpid(), DSH_CLI, HERMES_CLI, LEDGER)
    for raw in sys.stdin.buffer:
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