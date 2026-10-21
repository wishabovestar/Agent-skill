#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agent_router — Hermes ⇄ DSH 协同作业【动态路由】。

它解决什么
--------------------------------------------------------------------------
两台本地 Agent 产品同时装在这台机器上，各有各的长处：

    Hermes  会话/工具编排、技能、记忆与知识库、定时任务、消息平台网关、PPT/OCR…
    DSH     独立的 agent loop + 沙箱，适合「扔一个仓库进去、跑很久」的自主任务

问题是「这条活儿该谁干」全靠人临时判断。本模块把它变成**可观测、可审计、可复现**的决策：
先探可用性与预算，再按规则打分，落决策日志，最后**真的调起**对应一侧。

⭐ 设计纪律（来自本档累积的教训）
--------------------------------------------------------------------------
1. 每条规则必须同时给：① 观测量 ② 阈值 ③ **阈值附近怎么办**。
2. 硬闸先行：目标不可用时**绝不路由过去**（宁可留在本地慢一点，也不要发给一个死掉的对端）。
3. 默认留在 Hermes —— 与系统的「宁直答勿滥调度」一致。
4. 每次决策都落 JSONL：时间/决定/规则码/信号快照/**离阈值的距离**/结果。
5. 每条规则带 `reopen_if`：什么条件下该重新审视这条规则。

观测量与阈值（全部可测）
--------------------------------------------------------------------------
    dsh_available     dsh.cmd 存在且 `--version` 能跑       阈值: 布尔
    dsh_profile_ok    headless profile 存在                  阈值: 布尔
    dsh_lock          是否有并发运行占用锁                    阈值: 锁文件存在与否
    dsh_calls_today   今日已路由到 DSH 的次数                 阈值: 默认 20
    autonomy_score    任务的「自主长程」特征分（0-10）        阈值: >=6 倾向 DSH
    hermes_only_score 任务是否命中 Hermes 独有能力的特征分    阈值: >=1 即留在 Hermes（一票）

用法
--------------------------------------------------------------------------
    python agent_router.py signals                          # 探测信号
    python agent_router.py decide "<任务>" [--json]          # 只决策不执行
    python agent_router.py run "<任务>" [--dry-run]          # 决策 + 真调起
    python agent_router.py log [--tail 20]                   # 看决策日志
    python agent_router.py selftest                          # 自检（含负向）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

# ── 路径 ─────────────────────────────────────────────────────────────────────
HOME = Path(os.environ.get("USERPROFILE") or Path.home())
DSH_HOME = Path(os.environ.get("DSH_HOME") or (HOME / ".dsh"))

#: ⚠️ 启动器**不在** %USERPROFILE% 下 —— 本机桌面版装到了 `D:\Users\Administrator\...`
#: （装到 D 盘却保留了 Users 路径结构），所以必须多候选扫描，不能只信 HOME。
_CLI_CANDIDATES = [
    r"D:/Users/Administrator/AppData/Local/Programs/DeepSeek Harness/resources/runtime/cli/bin/dsh.cmd",
    r"C:/Users/Administrator/AppData/Local/Programs/DeepSeek Harness/resources/runtime/cli/bin/dsh.cmd",
]


def _resolve_dsh_cli() -> str:
    env = os.environ.get("DSH_CLI")
    if env and os.path.isfile(env):
        return env
    for c in _CLI_CANDIDATES:
        if os.path.isfile(c):
            return c
    # 兜底：在两个盘的 Users 下扫（只扫到 Programs 一层，不做全盘 find）
    import glob
    for pat in (r"D:/Users/*/AppData/Local/Programs/*/resources/runtime/cli/bin/dsh.cmd",
                r"C:/Users/*/AppData/Local/Programs/*/resources/runtime/cli/bin/dsh.cmd"):
        hits = glob.glob(pat)
        if hits:
            return hits[0]
    return os.environ.get("DSH_CLI") or _CLI_CANDIDATES[0]


DSH_CLI = _resolve_dsh_cli()
HERMES_EXE = os.environ.get("HERMES_EXE") or r"D:/hermes/hermes-data/bin/hermes.exe"


def _current_profile() -> str:
    """⭐ 基础设施中立：不能写死某个 profile。
    优先级：HERMES_ROUTE_PROFILE > HERMES_PROFILE > 从 HERMES_HOME 路径推断 > default"""
    for k in ("HERMES_ROUTE_PROFILE", "HERMES_PROFILE"):
        v = os.environ.get(k)
        if v:
            return v
    h = os.environ.get("HERMES_HOME") or ""
    m = re.search(r"[\\/]profiles[\\/]([^\\/]+)", h)
    return m.group(1) if m else "default"


HERMES_PROFILE = _current_profile()

STATE = Path(os.environ.get("AGENT_ROUTER_STATE") or r"D:/agent-shared/state")
LOG = STATE / "route_decisions.jsonl"
BUDGET = STATE / "route_budget.json"
LOCK = STATE / "dsh_run.lock"
CACHE = STATE / "signals_cache.json"

DAILY_DSH_CAP = int(os.environ.get("ROUTE_DSH_DAILY_CAP", "20"))
SIG_TTL = int(os.environ.get("ROUTE_SIGNAL_TTL", "300"))     # 秒

# ── Hermes 独有能力：命中任一 ⇒ 一票留在 Hermes（DSH 没有这些） ───────────────
HERMES_ONLY = {
    "消息平台": r"(发|推|通知).{0,6}(微信|wechat|qq|飞书|钉钉|群)|send.{0,10}(wechat|qq|telegram)",
    "定时任务": r"\bcron\b|定时|每天|每周|每日|周期性",
    "记忆/知识库": r"记忆|memor|知识库|\bkb\b|画像|profile\b|归档|论文库",
    "技能": r"技能|skill|SKILL\.md",
    "浏览器": r"浏览器|browser|打开网页|抓取网页",
    "PPT/文档": r"\bppt\b|pptx|幻灯片|word|docx|申报书",
    "本会话上下文": r"刚才|上面那|本轮|本会话|这个会话",
}

# ── 自主长程特征：加分（倾向 DSH） ─────────────────────────────────────────────
AUTONOMY = {
    "仓库/工程": (r"仓库|repo\b|项目目录|代码库|git\b", 2),
    "测试/构建循环": (r"跑测试|测试通过|build\b|编译|pytest|npm test|fix the tests|unit test", 3),
    "多步实现": (r"实现|实现一个|开发|重构|迁移|refactor|implement|migrate", 2),
    "长程自主": (r"自主|自己完成|跑很久|长程|autonomous|end.to.end|一口气", 2),
    "沙箱/隔离": (r"沙箱|sandbox|隔离环境|独立运行", 1),
    "大范围改动": (r"整个|全量|批量改|所有文件|whole repo", 1),
    "显式指名": (r"用\s*dsh|交给\s*dsh|deepseek harness|派给\s*dsh", 5),
}

# ── 任务 → 所需能力（能力闸：DSH 缺哪项 ⇒ 一票留在 Hermes） ────────────────────
NEEDS = {
    "shell.exec":     r"跑测试|跑一下测试|构建|\bbuild\b|编译|git\b|安装|pip\s|npm\s|\bmake\b|执行命令|跑脚本|测试通过|unit test|pytest",
    "net.fetch":      r"抓取|下载|爬取|爬虫|fetch|抓网页|搜索网页|打开网页|\burl\b|http",
    "kb.read":        r"知识库|\bkb\b|共享面|agent.shared",
    "mcp.consume":    r"\bmcp\b|tool server",
    "messaging.send": r"发消息|发到|通知|推送|微信|wechat|\bqq\b|飞书|钉钉",
    "cron.schedule":  r"定时|每天|每周|每日|cron",
    "skills.load":    r"技能\b|\bskill\b|SKILL\.md",
}

AUTONOMY_THRESHOLD = 6
AUTONOMY_NEAR = 4          # 4-5 分：接近阈值，记 near_threshold 并倾向保守留在 Hermes


# ── ⭐ 能力矩阵（按【实测】填，没测的一律 unknown，绝不猜） ───────────────────
# 证据字段写清"凭什么这么说"；reopen_if 写清"什么条件下这条会被推翻"。
# 未实测的能力 → "unknown" ⇒ 决策层一律【保守留在 Hermes】。
CAPS = {
    "shell.exec": {
        "hermes": "yes", "dsh": "BLOCKED",
        "evidence": "实测：DSH headless 报 `Error: sandbox escalation to \"danger-full-access\" "
                    "requires approval, but no approval channel is available` ⇒ 无人值守时 shell 不可用",
        "reopen_if": "DSH 提供无人值守审批通道或命令白名单",
    },
    "fs.read": {"hermes": "yes", "dsh": "yes",
                "evidence": "实测：DSH 写出并读回了 PWD_PROBE.txt（内容 ok）",
                "reopen_if": "—"},
    "fs.write": {"hermes": "yes", "dsh": "yes",
                 "evidence": "实测：DSH 在指定 cwd 落盘 3 B 文件成功",
                 "reopen_if": "—"},
    "agent.loop": {"hermes": "yes", "dsh": "yes",
                   "evidence": "实测：DSH 输出 reasoning 轨迹（规划→调用→自验证→回报），100.1s 跑完一问一答",
                   "reopen_if": "—"},
    "agent.longhorizon": {"hermes": "bounded", "dsh": "yes",
                          "evidence": "DSH `headless` = 答一个任务到静默为止、打印、退出；Hermes 会话受 max_turns 约束",
                          "reopen_if": "—"},
    "messaging.send": {"hermes": "yes", "dsh": "unknown",
                       "evidence": "Hermes 有平台网关（10 平台实测 connected）；DSH 侧是否有等价通道【未实测】",
                       "reopen_if": "实测 DSH 能发消息到目标平台"},
    "cron.schedule": {"hermes": "yes", "dsh": "unknown",
                      "evidence": "Hermes 有 cron 子系统（本机已跑 2 条）；DSH 侧未实测",
                      "reopen_if": "实测 DSH 侧定时能力"},
    "skills.load": {"hermes": "yes", "dsh": "no",
                    "evidence": "技能是 Hermes 概念（skills.external_dirs / SKILL.md）；DSH 用 Cordis 插件树，机制不同",
                    "reopen_if": "DSH 增加兼容 SKILL.md 的加载器"},
    "kb.read": {"hermes": "yes", "dsh": "unknown",
                "evidence": "共享面 D:/agent-shared/ 已建，但【DSH-the-agent 读它】未实测（此前只测了 DSH 的解释器跑桥脚本）",
                "reopen_if": "实测 DSH agent 调用 agent_bridge 取回 KB 条目"},
    "mcp.consume": {"hermes": "yes", "dsh": "yes",
                    "evidence": "源码级：DSH 有 mcp-client 插件（packages/mcp/mcp-client）；本机 .dsh/cordis.patch.yml 已挂 mcp-hermes",
                    "reopen_if": "—"},
    "net.fetch": {"hermes": "yes", "dsh": "unknown",
                  "evidence": "Hermes web 工具栈实测可用；DSH 侧网络能力【未实测】",
                  "reopen_if": "实测 DSH 取回一个 URL"},
}


def cap_of(feature: str, side: str) -> str:
    e = CAPS.get(feature) or {}
    return str(e.get(side, "unknown")).lower()


def caps_unavailable_for(side: str) -> list[str]:
    """该侧【明确不可用或未知】的能力（用于一票否决与保守处理）。"""
    bad = []
    for f, e in CAPS.items():
        v = str(e.get(side, "unknown")).lower()
        if v in ("no", "blocked", "unknown"):
            bad.append(f)
    return bad


# ── 状态与日志 ───────────────────────────────────────────────────────────────
def _ensure_state() -> None:
    STATE.mkdir(parents=True, exist_ok=True)


def _read_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(p: Path, obj) -> None:
    _ensure_state()
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def _log(rec: dict) -> None:
    _ensure_state()
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _today() -> str:
    return date.today().isoformat()


def budget_state() -> dict:
    b = _read_json(BUDGET, {})
    if b.get("day") != _today():
        b = {"day": _today(), "dsh_calls": 0, "hermes_calls": 0}
        _write_json(BUDGET, b)
    return b


def bump_budget(which: str) -> dict:
    b = budget_state()
    b[which] = int(b.get(which, 0)) + 1
    _write_json(BUDGET, b)
    return b


# ── 信号探测 ─────────────────────────────────────────────────────────────────
def _dsh_version(timeout: int = 90) -> tuple[bool, str]:
    if not os.path.isfile(DSH_CLI):
        return False, "launcher-not-found"
    try:
        p = subprocess.run([DSH_CLI, "--version"], capture_output=True, text=True,
                           timeout=timeout, shell=False)
        v = (p.stdout or "").strip().splitlines()
        return (p.returncode == 0, v[0] if v else f"rc={p.returncode}")
    except Exception as exc:
        return False, f"{type(exc).__name__}"


def signals(use_cache: bool = True) -> dict:
    """探测所有观测量。带 TTL 缓存（默认 300s），避免每次决策都去启 CLI。"""
    if use_cache:
        c = _read_json(CACHE, {})
        if c.get("ts") and (time.time() - c["ts"]) < SIG_TTL:
            c["cached"] = True
            return c
    ok, ver = _dsh_version()
    sig = {
        "ts": time.time(),
        "cached": False,
        "dsh_available": bool(ok),
        "dsh_version": ver,
        "dsh_cli": DSH_CLI,
        "dsh_profile_ok": (DSH_HOME / "profiles" / "headless").is_dir(),
        "dsh_lock": LOCK.exists(),
        "dsh_calls_today": budget_state().get("dsh_calls", 0),
        "dsh_daily_cap": DAILY_DSH_CAP,
        "hermes_exe_ok": os.path.isfile(HERMES_EXE),
        "hermes_profile": HERMES_PROFILE,
    }
    _write_json(CACHE, sig)
    return sig


# ── 打分与决策 ───────────────────────────────────────────────────────────────
def score_task(task: str) -> dict:
    t = task or ""
    hits_hermes = {k: m.group(0)[:40] for k, p in HERMES_ONLY.items()
                   if (m := re.search(p, t, re.I))}
    autos, total = [], 0
    for k, (p, w) in AUTONOMY.items():
        if re.search(p, t, re.I):
            autos.append({"feature": k, "weight": w})
            total += w
    needs = sorted({c for c, p in NEEDS.items() if re.search(p, t, re.I)})
    return {"autonomy_score": total, "autonomy_hits": autos,
            "hermes_only_hits": hits_hermes, "task_len": len(t), "needs": needs}


def decide(task: str, sig: dict | None = None, sc: dict | None = None) -> dict:
    """返回决策记录（含规则码 + 阈值距离）。规则顺序 = 优先级。"""
    sig = sig or signals()
    sc = sc or score_task(task)
    a, h = sc["autonomy_score"], sc["hermes_only_hits"]

    def mk(exec_side, code, reason, extra=None):
        d = {"ts": datetime.now().isoformat(timespec="seconds"), "task": (task or "")[:300],
             "decision": exec_side, "rule": code, "reason": reason,
             "signals": {k: sig.get(k) for k in
                         ("dsh_available", "dsh_version", "dsh_lock", "dsh_calls_today",
                          "dsh_daily_cap", "dsh_profile_ok", "cached")},
             "scores": sc,
             "threshold_distance": {
                 "autonomy": f"{a} vs >={AUTONOMY_THRESHOLD} (Δ{a - AUTONOMY_THRESHOLD:+d})",
                 "budget": f"{sig.get('dsh_calls_today')} vs <{sig.get('dsh_daily_cap')}"},
             "needs": sc.get("needs") or [],
             "reopen_if": []}
        if extra:
            d.update(extra)
        return d

    # 硬闸 0：目标不可用
    if not sig.get("dsh_available"):
        return mk("HERMES", "G0-dsh-unavailable",
                  f"DSH 不可用（{sig.get('dsh_version')}）⇒ 绝不路由到死端",
                  {"reopen_if": ["dsh.cmd 可执行且 --version 返回 0"]})
    if not sig.get("dsh_profile_ok"):
        return mk("HERMES", "G0b-no-headless-profile",
                  "缺少 headless profile ⇒ 无法做一次性自主运行",
                  {"reopen_if": ["$DSH_HOME/profiles/headless 存在"]})

    # 一票否决 1：Hermes 独有
    if h:
        return mk("HERMES", "R1-hermes-only",
                  "命中 Hermes 独有能力的占位：" + "、".join(h),
                  {"reopen_if": ["DSH 侧出现等价能力（如消息通道/记忆/技能）"]})

    # ⭐ 能力闸 1b：任务需要的能力，DSH 侧【明确没有或未实测】⇒ 一票留在 Hermes
    #    （只对"本来会派给 DSH"的任务生效；HERMES_ONLY 已拦掉大部分，这里补漏）
    needs = sc.get("needs") or []
    gap = [c for c in needs if cap_of(c, "dsh") in ("no", "blocked", "unknown")]
    if gap:
        detail = "；".join("%s(dsh=%s)" % (c, cap_of(c, "dsh").upper()) for c in gap)
        return mk("HERMES", "C1-capability-gap",
                  "任务所需能力 DSH 侧不具备或未实测 ⇒ 不派给它：" + detail,
                  {"capability_gap": gap,
                   "reopen_if": [f"实测 DSH 具备 {c}（见 CAPS[{c}].reopen_if）" for c in gap]})

    # 预算闸 2
    if int(sig.get("dsh_calls_today", 0)) >= int(sig.get("dsh_daily_cap", DAILY_DSH_CAP)):
        return mk("HERMES", "R2-budget-exhausted",
                  f"DSH 今日配额用尽（{sig.get('dsh_calls_today')}/{sig.get('dsh_daily_cap')}）"
                  " ⇒ 降级留在本地（可用 ROUTE_DSH_DAILY_CAP 调整）",
                  {"reopen_if": ["次日或调高 ROUTE_DSH_DAILY_CAP"]})

    # 并发闸 3
    if sig.get("dsh_lock"):
        return mk("HERMES", "R3-dsh-busy",
                  "DSH 正被另一个运行占用（锁存在）⇒ 避免并发撞车",
                  {"reopen_if": ["锁释放（或确需并发，改走独立 workspace）"]})

    # 主判定 4/5：自主长程分
    if a >= AUTONOMY_THRESHOLD:
        return mk("DSH", "R4-autonomous-longhorizon",
                  f"自主长程特征 {a}>={AUTONOMY_THRESHOLD}，命中：" +
                  "、".join(f"{x['feature']}(+{x['weight']})" for x in sc["autonomy_hits"]),
                  {"reopen_if": ["实测 DSH 侧失败率高于本地（看决策日志的 outcome）"]})
    if AUTONOMY_NEAR <= a < AUTONOMY_THRESHOLD:
        return mk("HERMES", "R5-near-threshold",
                  f"自主分 {a} 落在 [{AUTONOMY_NEAR},{AUTONOMY_THRESHOLD}) 的模糊带 ⇒ "
                  "保守留在本地；若你明确要长程自主，请把意图写进任务（如『一口气跑完』）",
                  {"reopen_if": [f"任务描述更明确，或把阈值下调到 {AUTONOMY_NEAR}"]})

    # 默认
    return mk("HERMES", "R6-default-local",
              f"无足够自主特征（{a}<{AUTONOMY_NEAR}）⇒ 默认留在 Hermes（宁直答勿滥调度）",
              {"reopen_if": ["任务出现仓库/测试/多步实现等特征"]})


# ── 执行 ─────────────────────────────────────────────────────────────────────
def _run_cmd(cmd: list[str], timeout: int, cwd: str | None = None) -> tuple[int, str, str, float]:
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return p.returncode, p.stdout or "", p.stderr or "", time.time() - t0
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s", time.time() - t0
    except Exception as exc:
        return 1, "", f"{type(exc).__name__}: {exc}", time.time() - t0


def resolve_cwd(explicit: str | None = None) -> str:
    """⭐ 必须显式给 cwd —— `dsh headless` **没有** workspace/cwd 选项（只有 --json / --session-id），
    它写的文件落在【继承来的进程 cwd】里。不指定就会落到调用方 shell 当时的目录（实测落到
    cache/scratch），使路由过去的任务产物散落到意料之外。默认给一个专用共享工作区。"""
    c = explicit or os.environ.get("AGENT_ROUTER_DSH_CWD") or r"D:/agent-shared/workspace"
    try:
        os.makedirs(c, exist_ok=True)
    except Exception:
        return os.getcwd()
    return c


def execute(dec: dict, task: str, dry_run: bool, timeout: int, cwd: str | None = None) -> dict:
    side = dec["decision"]
    if side == "DSH":
        cmd = [DSH_CLI, "--profile", "headless", task]
    else:
        cmd = [HERMES_EXE, "-p", HERMES_PROFILE, "-z", task]
    dec["cmd"] = cmd if side == "DSH" else [cmd[0], "-p", HERMES_PROFILE, "-z", "<task>"]
    if dry_run:
        dec["outcome"] = "dry-run"
        dec["cwd"] = cwd
        return dec
    # DSH 分支：加锁防并发
    if side == "DSH":
        STATE.mkdir(parents=True, exist_ok=True)
        LOCK.write_text(json.dumps({"pid": os.getpid(), "ts": time.time()}), encoding="utf-8")
    try:
        rc, out, err, dur = _run_cmd(cmd, timeout, cwd=cwd)
    finally:
        if side == "DSH":
            LOCK.unlink(missing_ok=True)
    dec["cwd"] = cwd or os.getcwd()
    dec["outcome"] = "ok" if rc == 0 else f"error rc={rc}"
    dec["duration_s"] = round(dur, 1)
    dec["stdout_head"] = out.strip()[:1200]
    if err.strip():
        dec["stderr_head"] = err.strip()[:400]
    bump_budget("dsh_calls" if side == "DSH" else "hermes_calls")
    return dec


# ── CLI ──────────────────────────────────────────────────────────────────────
def cmd_signals(a) -> int:
    s = signals(use_cache=not a.no_cache)
    print(json.dumps(s, ensure_ascii=False, indent=2))
    return 0


def cmd_decide(a) -> int:
    d = decide(a.task)
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
    else:
        print(f"  决定    : {d['decision']}   （规则 {d['rule']}）")
        print(f"  理由    : {d['reason']}")
        print(f"  阈值距离: {d['threshold_distance']}")
        if d["scores"]["autonomy_hits"]:
            print("  自主特征: " + ", ".join(f"{x['feature']}+{x['weight']}" for x in d["scores"]["autonomy_hits"]))
        print(f"  reopen_if: {d['reopen_if']}")
    _log(d)
    return 0


def cmd_run(a) -> int:
    s = signals()
    d = decide(a.task, sig=s)
    cwd = resolve_cwd(getattr(a, "cwd", None))
    print(f"  → {d['decision']}  [{d['rule']}]  {d['reason']}")
    print(f"  cwd: {cwd}")
    d = execute(d, a.task, a.dry_run, a.timeout, cwd=cwd)
    print(f"  执行    : {d['outcome']}"
          + (f"  用时 {d.get('duration_s')}s" if d.get("duration_s") else ""))
    if d.get("stdout_head"):
        print("  --- stdout ---"); print("  " + d["stdout_head"].replace("\n", "\n  ")[:1500])
    if d.get("stderr_head"):
        print("  --- stderr ---"); print("  " + d["stderr_head"][:400])
    _log(d)
    return 0 if d["outcome"] in ("ok", "dry-run") else 1


def cmd_log(a) -> int:
    if not LOG.is_file():
        print("  (还没有决策日志)"); return 0
    lines = LOG.read_text(encoding="utf-8").splitlines()
    print(f"  共 {len(lines)} 条决策，显示最后 {a.tail} 条：")
    for ln in lines[-a.tail:]:
        try:
            r = json.loads(ln)
        except Exception:
            continue
        print("   %s  %-6s %-22s %s | %s" % (
            r.get("ts", "")[11:], r.get("decision"), r.get("rule"),
            (r.get("outcome") or "-")[:14], (r.get("task") or "")[:54]))
    return 0


def cmd_caps(a) -> int:
    """打印能力矩阵（含证据与翻转条件）—— 这是"按能力分配"的判据表。"""
    only = getattr(a, "side", None)
    sides = [only] if only else ["hermes", "dsh"]
    if getattr(a, "json", False):
        print(json.dumps({"caps": CAPS, "unavailable_dsh": caps_unavailable_for("dsh")},
                         ensure_ascii=False, indent=1)); return 0
    print("  能力矩阵（HERMES vs DSH）—— 只有【实测过】的才敢写 yes/no；没测的一律 unknown")
    print()
    print("  %-20s %-10s %-12s %s" % ("能力", "HERMES", "DSH", "翻转条件"))
    print("  " + "-" * 96)
    for f, e in CAPS.items():
        line = {k: str(e.get(k, "unknown")) for k in ("hermes", "dsh")}
        if only == "dsh": line["hermes"] = "—"
        if only == "hermes": line["dsh"] = "—"
        print("  %-20s %-10s %-12s %s" % (f, line["hermes"], line["dsh"], str(e.get("reopen_if", "—"))[:44]))
    print()
    bad = caps_unavailable_for("dsh")
    print("  ⚠️ DSH 侧【不可用或未实测】的能力 %d 项 ⇒ 需要这些能力的任务一律留在 Hermes：" % len(bad))
    print("     " + "、".join(bad))
    print()
    print("  ⭐ 证据（凭什么这么判）：")
    for f, e in CAPS.items():
        print("     %-20s %s" % (f, str(e.get("evidence", "—"))[:150]))
    return 0


def cmd_selftest(a) -> int:
    print("== agent_router 自检 ==")
    ok = True
    s = signals()
    print(f"  DSH 可用: {s['dsh_available']} ({s['dsh_version']})")
    print(f"  headless profile: {s['dsh_profile_ok']}")
    print(f"  今日 DSH 调用: {s['dsh_calls_today']}/{s['dsh_daily_cap']}")

    cases = [
        ("把今天的测试报告发到微信群", "HERMES", "R1-hermes-only"),
        ("查看知识库里关于极片的条目", "HERMES", "R1-hermes-only"),
        ("帮我实现一个功能", "HERMES", None),
        # ⭐ 这条【期望已更新】：含"跑测试"⇒ 需要 shell ⇒ DSH 沙箱不具备 ⇒ 能力闸拦下。
        #    以前它被派给 DSH（R4）；能力矩阵落地后【正确的行为是留在 Hermes】。
        ("clone 这个仓库然后跑测试，一直修到全绿，用 dsh 一口气做完", "HERMES", "C1-capability-gap"),
    ]
    for task, want, wantrule in cases:
        d = decide(task, sig=s)
        good = (d["decision"] == want) and (wantrule is None or d["rule"] == wantrule)
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] {task[:40]:42s} -> {d['decision']:6s} {d['rule']}")
        _log(d)

    # ⭐ 能力闸：需要 shell 的任务即使显式指名 dsh，也必须留在 Hermes（DSH 沙箱禁 shell）
    d = decide("用 dsh 一口气跑测试并修到全绿", sig=s)
    cap1 = d["decision"] == "HERMES" and d["rule"] == "C1-capability-gap"
    ok &= cap1
    print(f"  [{'OK' if cap1 else 'FAIL'}] 能力闸·shell 类任务 ⇒ {d['decision']} {d['rule']}  "
          f"gap={d.get('capability_gap')}")

    # ⭐ 能力闸的【负向】：不需要 shell 的同类任务，仍应派给 DSH（证明能力闸不是恒真）
    d = decide("用 dsh 一口气做完：把这个目录里的三个文件合并成一个 md", sig=s)
    cap2 = d["decision"] == "DSH"
    ok &= cap2
    print(f"  [{'OK' if cap2 else 'FAIL'}] 能力闸负向·纯文件任务（不涉 shell）⇒ {d['decision']} {d['rule']}")

    # 负向：不可用时绝不路由 DSH
    dead = dict(s); dead["dsh_available"] = False; dead["dsh_version"] = "PROBE-DEAD"
    d = decide("clone 仓库跑测试一直修到全绿，用 dsh 一口气做完", sig=dead)
    neg1 = d["decision"] == "HERMES" and d["rule"] == "G0-dsh-unavailable"
    ok &= neg1
    print(f"  [{'OK' if neg1 else 'FAIL'}] 负向·DSH 不可用 ⇒ {d['decision']} {d['rule']}")

    # 负向：预算耗尽时降级（⚠️ 必须用【不触发能力闸】的任务 —— 含 shell 的任务会先被 C1 拦下）
    poor = dict(s); poor["dsh_calls_today"] = poor["dsh_daily_cap"] + 1
    d = decide("用 dsh 一口气做完：把这个目录里的三个文件合并成一个 md", sig=poor)
    neg2 = d["decision"] == "HERMES" and d["rule"] == "R2-budget-exhausted"
    ok &= neg2
    print(f"  [{'OK' if neg2 else 'FAIL'}] 负向·预算用尽 ⇒ {d['decision']} {d['rule']}")

    print("\n  " + ("✅ 全部通过" if ok else "❌ 有失败项"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(prog="agent_router", description="Hermes ⇄ DSH 动态路由")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("signals"); s.add_argument("--no-cache", action="store_true"); s.set_defaults(fn=cmd_signals)
    d = sub.add_parser("decide"); d.add_argument("task"); d.add_argument("--json", action="store_true"); d.set_defaults(fn=cmd_decide)
    r = sub.add_parser("run"); r.add_argument("task"); r.add_argument("--dry-run", action="store_true")
    r.add_argument("--timeout", type=int, default=900)
    r.add_argument("--cwd", default=None,
                   help="执行时的工作目录（dsh headless 无 workspace 选项，只能靠进程 cwd 决定产物落点）；"
                        "默认 D:/agent-shared/workspace，可用 AGENT_ROUTER_DSH_CWD 覆盖")
    r.set_defaults(fn=cmd_run)
    l = sub.add_parser("log"); l.add_argument("--tail", type=int, default=20); l.set_defaults(fn=cmd_log)
    c = sub.add_parser("caps"); c.add_argument("--side", choices=["hermes", "dsh"], default=None)
    c.add_argument("--json", action="store_true"); c.set_defaults(fn=cmd_caps)
    sub.add_parser("selftest").set_defaults(fn=cmd_selftest)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
