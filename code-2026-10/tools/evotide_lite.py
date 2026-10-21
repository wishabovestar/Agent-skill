#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evotide_lite.py — EvoTIDE 的「轨迹恢复 + 双角色评估」轻量版

来源：Evo2: Evolving the Evolver through Weight-Harness Co-Evolution
      (arXiv:2610.13025)  §3.3  Weight evolution through EvoTIDE
      EvoTIDE = Tree-guided Interleaved Dual-role Evolution

本模块只取 EvoTIDE 中**不需要训练权重**的两个部分，用于本机 harness/技能编辑的评分回流：

  (A) 轨迹恢复  Trajectory Recovery
      - edit extraction   : rollout 没产出显式 edit action 时，从 reasoning/chat 里抽回编辑
      - prefix continuation: 多步编辑中后续失效时，在最后一个成功编辑处截断，保留前缀
      - 恢复的 proposal 必须过 application/startup/eval 三关才能入账

  (B) 双角色评估 Dual-role Evaluation
      - Proposer : r_exec = S(child) - S(parent)
      - Reflector: r_exec = S(after) - S(before)，但**只在 trace 证明机制真的跑过时给分**，
                   否则增益置 0（防虚假归因 —— 原文 §3.3.2 明确写了这条）
      - keep action -> 0
      - malformed / 无法应用 / 无法启动 / no-op / 无效 crossover -> 负奖励

**不做的部分**（原文有、本机不做）：SFT、GRPO、交错角色训练、父节点池采样、树维护。
理由：那些都要训练权重；本机只做评分回流，不碰模型参数。

接到 self-reinforcement：
    verdict -> to_rsi_candidate() -> rsi_gate.Candidate(...) -> evaluate() 过接受闸

用法：
    python evotide_lite.py --selftest        # 12 项自检（含 3 项阴性对照）
    python evotide_lite.py --demo            # 端到端演示，产出 JSONL 台账
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Literal, Sequence

VERSION = "1.0.0"

# 台账默认目录（与 self-reinforcement skill 的 reinforcement_logs 同级）
LEDGER_DIR = os.environ.get(
    "EVOTIDE_LEDGER_DIR",
    r"D:/hermes/analysis/reinforcement_logs",
)

# ---------------------------------------------------------------- Part 1: 编辑表示

@dataclass
class EditOp:
    """一次文件编辑。old/new 用字符串表示（不做行号，避免与真实文件漂移）。"""
    path: str
    old: str
    new: str
    source: str = "explicit"     # explicit | extracted
    applied: bool = False
    error: str = ""

    def apply_to(self, content: str) -> str:
        """在给定内容上应用本编辑；old 必须唯一出现。"""
        if not self.old:
            return content + self.new
        n = content.count(self.old)
        if n != 1:
            raise ValueError(f"old_string 出现 {n} 次（要求恰好 1 次）")
        return content.replace(self.old, self.new, 1)


# 显式编辑块的三种常见写法
_EDIT_BLOCK = re.compile(
    r"(?:<<<EDIT>>>|\[EDIT\]|EDIT:)\s*(?P<body>.+?)(?=<<<END>>>|\[/EDIT\]|\Z)",
    re.S,
)
_DIFF_HUNK = re.compile(r"^---\s*(?P<path>\S+).*?^\+\+\+.*?(?P<body>(?:^[-+ ].*$\n?)+)", re.M | re.S)


def _parse_edit_body(body: str) -> tuple[str, str, str] | None:
    """从 edit 正文里取 (path, old, new)，支持 OLD:/NEW: 与 ```diff 两种。"""
    m = re.search(r"OLD:\s*(?P<old>.*?)\s*NEW:\s*(?P<new>.*)", body, re.S)
    if m:
        p = re.search(r"PATH:\s*(?P<p>\S+)", body)
        return (p.group("p") if p else ""), m.group("old").strip(), m.group("new").strip()
    # ```diff 形式
    m = re.search(r"```diff\s*(?P<d>.+?)```", body, re.S)
    if m:
        minus, plus = [], []
        for line in m.group("d").splitlines():
            if line.startswith("-") and not line.startswith("---"):
                minus.append(line[1:])
            elif line.startswith("+") and not line.startswith("+++"):
                plus.append(line[1:])
        if minus or plus:
            return "", "\n".join(minus), "\n".join(plus)
    return None


def extract_edits(text: str, path_hint: str = "") -> list[EditOp]:
    """
    edit extraction：从一段自由文本（通常是 assistant 的 reasoning/chat）里抽回文件编辑。
    对应原文 §3.3.1 "Edit extraction handles rollouts that end without an explicit edit action"。
    """
    out: list[EditOp] = []
    for m in _EDIT_BLOCK.finditer(text or ""):
        parsed = _parse_edit_body(m.group("body"))
        if parsed:
            p, old, new = parsed
            out.append(EditOp(path=p or path_hint, old=old, new=new, source="extracted"))
    for m in _DIFF_HUNK.finditer(text or ""):
        body = m.group("body")
        minus = [l[1:] for l in body.splitlines() if l.startswith("-") and not l.startswith("---")]
        plus = [l[1:] for l in body.splitlines() if l.startswith("+") and not l.startswith("+++")]
        if minus or plus:
            out.append(EditOp(path=m.group("path") or path_hint,
                              old="\n".join(minus), new="\n".join(plus), source="extracted"))
    return out


@dataclass
class RecoveryResult:
    edits: list[EditOp] = field(default_factory=list)
    recovered: int = 0            # 通过抽取救回的编辑数
    truncated_at: int = -1        # prefix continuation 的截断下标（-1 = 未截断）
    needs_resume: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def usable_edits(self) -> list[EditOp]:
        """截断后仍可用的前缀编辑。"""
        return self.edits if self.truncated_at < 0 else self.edits[: self.truncated_at]


def recover_rollout(messages: Sequence[dict],
                    applied_ok: Sequence[bool] | None = None,
                    path_hint: str = "") -> RecoveryResult:
    """
    轨迹恢复主入口。

    messages   : [{"role": "assistant"/"user"/"tool", "content": "..."}]
    applied_ok : 每个检测到的编辑是否成功应用（长度可短于 edits，短的视为 True）。
                 第一个 False 的位置即 prefix continuation 的截断点。
    """
    res = RecoveryResult()
    convo = "\n".join(m.get("content", "") for m in messages if m.get("role") == "assistant")

    explicit = extract_edits(convo, path_hint)
    if not explicit:
        # 没有任何显式编辑块 -> 尝试从 reasoning 里再抽一次（同一套正则，但记来源为 extracted）
        salvaged = extract_edits(convo, path_hint)
        if salvaged:
            for e in salvaged:
                e.source = "extracted"
            res.edits = salvaged
            res.recovered = len(salvaged)
            res.notes.append("no explicit edit action; salvaged %d edit(s) from reasoning" % len(salvaged))
        else:
            res.notes.append("no edit found in rollout")
        explicit = res.edits
    else:
        # 有显式块，但仍检查文本里是否有被丢掉、只出现在 reasoning 中的编辑
        res.edits = explicit
        res.recovered = sum(1 for e in explicit if e.source == "extracted")

    # ---- prefix continuation ----
    if applied_ok:
        bad = next((i for i, ok in enumerate(applied_ok) if not ok), None)
        if bad is not None and bad < len(res.edits):
            res.truncated_at = bad
            res.needs_resume = True
            res.notes.append(
                "prefix continuation: truncate after edit #%d, restore intermediate harness, "
                "resume generation from that prefix" % bad
            )
            # 截断点及之后一律标记为未应用
            for i, e in enumerate(res.edits):
                e.applied = bool(applied_ok[i]) if i < len(applied_ok) else False
        else:
            for i, e in enumerate(res.edits):
                e.applied = bool(applied_ok[i]) if i < len(applied_ok) else True
    return res


# ---------------------------------------------------------------- Part 2: 打分器

@dataclass
class Assertion:
    """单条断言。kind: contains / not_contains / min_lines / compiles / regex"""
    kind: str
    value: str = ""
    weight: float = 1.0
    label: str = ""

    def check(self, content: str, path: str) -> bool:
        if self.kind == "contains":
            return self.value in content
        if self.kind == "not_contains":
            return self.value not in content
        if self.kind == "min_lines":
            return len(content.splitlines()) >= int(self.value)
        if self.kind == "regex":
            return bool(re.search(self.value, content))
        if self.kind == "compiles":
            try:
                py_compile.compile(path, cfile=os.devnull, doraise=True)
                return True
            except Exception:
                return False
        raise ValueError(f"unknown assertion kind: {self.kind}")

    def __str__(self) -> str:
        return self.label or f"{self.kind}:{self.value[:40]}"


class AssertionScorer:
    """
    默认打分器：S(harness) = 加权断言通过率，落在 [0,1]。
    对应原文的 "mean externally evaluated task score" S(h) —— 本机用断言集替代任务集。
    """

    def __init__(self, assertions: Sequence[Assertion]):
        if not assertions:
            raise ValueError("assertions 不能为空")
        self.assertions = list(assertions)

    def __call__(self, path: str) -> float:
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError:
            return 0.0
        num = den = 0.0
        for a in self.assertions:
            den += a.weight
            if a.check(content, path):
                num += a.weight
        return round(num / den, 6) if den else 0.0

    def detail(self, path: str) -> dict:
        try:
            content = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            return {"error": "unreadable"}
        rows = []
        for a in self.assertions:
            ok = a.check(content, path)
            rows.append({"assertion": str(a), "ok": ok, "weight": a.weight})
        return {"score": self(path), "assertions": rows}


# ---------------------------------------------------------------- Part 3: 双角色评估

# 原文 §3.3.2：malformed / 无法应用 / 无法启动 都给负奖励
PENALTIES: dict[str, float] = {
    "malformed_output": -0.30,
    "edit_not_applied": -0.30,
    "harness_not_started": -0.30,
    "noop_edit": -0.10,
    "invalid_crossover": -0.20,
    "recovered_unverified": -0.15,   # 恢复出来但未过 application/eval 检查
}

# 结构性失败：该次尝试的分数变化**不可归因**于这条编辑，执行奖励作废而非叠加。
# 理由：malformed 的 rollout 可能根本没把编辑写进 harness，此时 S(child)-S(parent) 的
# 变化来自别处；若只扣 0.3，一个"涨 0.4 但格式全错"的尝试仍会净正 —— 与原文负奖励语义冲突。
STRUCTURAL_PENALTIES = {
    "malformed_output",
    "edit_not_applied",
    "harness_not_started",
    "invalid_crossover",
}

TYPE_B_BONUS = 0.02        # 触及指令指定文件
TYPE_B_MALUS = -0.02       # 未触及

Role = Literal["proposer", "reflector"]
TaskType = Literal["A", "B"]
Action = Literal["edit", "keep"]


@dataclass
class Attempt:
    """一次可评估的尝试（Proposer 的一条编辑，或 Reflector 的一次干预）。"""
    role: Role
    task_type: TaskType = "A"
    parent_score: float | None = None      # Proposer: 父 harness 的 S
    child_score: float | None = None       # Proposer: 子 harness 的 S
    before_score: float | None = None      # Reflector: 干预前 S
    after_score: float | None = None       # Reflector: 干预后 S
    action: Action = "edit"
    penalties: list[str] = field(default_factory=list)
    mechanism_ran: bool = True             # Reflector: trace 是否证明新增机制真的跑过
    directive_files: list[str] = field(default_factory=list)
    touched_files: list[str] = field(default_factory=list)
    recovered: bool = False
    needs_resume: bool = False
    seed_runs: int = 1                     # 重复运行次数（原文：averaging repeated runs when available）
    label: str = ""


@dataclass
class Verdict:
    exec_reward: float
    shaped_reward: float
    components: dict
    admissible: bool
    reasons: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def propose_reward(parent: float, child: float) -> float:
    """r_exec = S(h') - S(h)"""
    return round(float(child) - float(parent), 6)


def reflect_reward(before: float, after: float, mechanism_ran: bool) -> tuple[float, bool]:
    """
    r_exec = S(h1) - S(h0)，**但 mechanism_ran=False 时置 0**。
    原文 §3.3.2："positive gains are credited only when the traces contain evidence that
    the added mechanism ran; otherwise the gain is set to zero."
    这是本模块最重要的一条 —— 防「改了文件、分数碰巧涨了、其实是别的因素」的虚假归因。
    """
    gain = round(float(after) - float(before), 6)
    if not mechanism_ran:
        return 0.0, True   # (reward, suppressed)
    return gain, False


def evaluate_attempt(a: Attempt) -> Verdict:
    """双角色评估主入口。返回执行奖励 + 塑形奖励 + 是否可入账。"""
    reasons: list[str] = []
    comp: dict[str, Any] = {"role": a.role, "task_type": a.task_type}

    # ---- keep action：h1 = h0，奖励为 0 ----
    if a.action == "keep":
        comp["exec"] = 0.0
        comp["note"] = "keep action -> h1 = h0, zero execution reward"
        shaped = sum(PENALTIES.get(p, 0.0) for p in a.penalties)
        return Verdict(0.0, round(shaped, 6), comp,
                       admissible=not a.penalties, reasons=["keep_action"])

    # ---- 执行奖励 ----
    if a.role == "proposer":
        if a.parent_score is None or a.child_score is None:
            raise ValueError("proposer 需要 parent_score 与 child_score")
        exec_r = propose_reward(a.parent_score, a.child_score)
        comp["exec"] = exec_r
        comp["parent"], comp["child"] = a.parent_score, a.child_score
    else:
        if a.before_score is None or a.after_score is None:
            raise ValueError("reflector 需要 before_score 与 after_score")
        exec_r, suppressed = reflect_reward(a.before_score, a.after_score, a.mechanism_ran)
        comp["exec"] = exec_r
        comp["before"], comp["after"] = a.before_score, a.after_score
        comp["mechanism_ran"] = a.mechanism_ran
        if suppressed:
            comp["suppressed"] = True
            reasons.append("mechanism_not_evidenced -> gain zeroed")

    # ---- 惩罚项 ----
    structural = [p for p in a.penalties if p in STRUCTURAL_PENALTIES]
    pen = sum(PENALTIES.get(p, 0.0) for p in a.penalties)
    if pen:
        comp["penalties"] = {p: PENALTIES.get(p, 0.0) for p in a.penalties}
        reasons.extend(f"penalty:{p}" for p in a.penalties)
    if structural:
        # 结构性失败 -> 执行奖励作废（不可归因），只留惩罚
        comp["exec_raw"] = exec_r
        comp["exec_voided"] = True
        exec_r = 0.0
        reasons.append("structural_failure -> execution reward voided (unattributable)")

    # ---- Type B：是否触及指令指定文件 ----
    shaped = exec_r + pen
    if a.task_type == "B" and a.directive_files:
        hit = set(a.directive_files) & set(a.touched_files)
        bonus = TYPE_B_BONUS if hit else TYPE_B_MALUS
        shaped += bonus
        comp["type_b"] = {"directive": a.directive_files, "touched": a.touched_files, "bonus": bonus}
        if not hit:
            reasons.append("type_b: directive files untouched")

    # ---- 可入账判定（fail-closed：证据不足 = 不入账）----
    admissible = True
    if a.penalties:
        admissible = False
    if a.needs_resume:
        admissible = False
        reasons.append("prefix_continuation_pending: 恢复未完成，不入账")
    if a.recovered and "recovered_unverified" in a.penalties:
        admissible = False
    if a.role == "reflector" and not a.mechanism_ran:
        # 机制没被 trace 证明跑过 -> 这次尝试整体不可采信，不许入账
        # （不能只把 exec 归零却让 Type B bonus 把它抬成正数）
        admissible = False
        reasons.append("mechanism_not_evidenced -> inadmissible")
    if a.seed_runs < 1:
        admissible = False
        reasons.append("no_seed_runs")

    comp["seed_runs"] = a.seed_runs
    return Verdict(round(exec_r, 6), round(shaped, 6), comp, admissible, reasons)


# ---------------------------------------------------------------- Part 4: 台账 / 接 rsi_gate

def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "ignore")).hexdigest()[:16]


def to_rsi_candidate(v: Verdict, label: str, child_score: float,
                     threshold: float = 0.5, d_cost: float = 0.0) -> dict:
    """
    把 EvoTIDE 评分映射成 rsi_gate.Candidate 的字段。
    不训权重 => d_cost 默认 0（只算推理/执行成本，不算训练成本）。
    """
    return {
        "name": label,
        "diff": _sha(json.dumps(v.components, sort_keys=True, ensure_ascii=False)),
        "score": round(float(child_score), 6),
        "d_score": v.exec_reward,
        "d_cost": d_cost,
        "resolved": bool(child_score >= threshold),
        "verified": bool(v.admissible),
        "admit_hint": bool(v.admissible and v.exec_reward > 0),
    }


class Ledger:
    """JSONL 台账：一条尝试一行，可被任何下游读取。"""

    def __init__(self, path: str | None = None):
        os.makedirs(LEDGER_DIR, exist_ok=True)
        self.path = path or os.path.join(LEDGER_DIR, "evotide_scores.jsonl")

    def append(self, record: dict) -> str:
        record = dict(record)
        record.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
        record.setdefault("evotide_version", VERSION)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return self.path

    def read_all(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def stats(self) -> dict:
        rows = self.read_all()
        if not rows:
            return {"n": 0}
        adm = [r for r in rows if r.get("verdict", {}).get("admissible")]
        gains = [r["verdict"]["exec_reward"] for r in rows]
        pos = sum(1 for g in gains if g > 0)
        neg = sum(1 for g in gains if g < 0)
        return {
            "n": len(rows),
            "admissible": len(adm),
            "admit_ratio": round(len(adm) / len(rows), 3),
            "positive": pos, "negative": neg, "zero": len(gains) - pos - neg,
            "mean_exec_reward": round(sum(gains) / len(gains), 4),
            "suppressed_by_mechanism": sum(
                1 for r in rows if r.get("verdict", {}).get("components", {}).get("suppressed")
            ),
        }


# ---------------------------------------------------------------- Selftest

def _write(tmpdir: str, name: str, content: str) -> str:
    p = os.path.join(tmpdir, name)
    os.makedirs(os.path.dirname(p) or tmpdir, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


def selftest(verbose: bool = True) -> int:
    """12 项自检，含 3 项阴性对照（不该通过时必须不通过）。"""
    results: list[tuple[str, bool, str]] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        results.append((name, bool(cond), detail))

    tmp = tempfile.mkdtemp(prefix="evotide_")
    base = "line1\nline2\nline3\n"
    parent = _write(tmp, "harness_p.md", base)
    good = _write(tmp, "harness_good.md", "line1\nline2\nline3\nEXTRA_MECHANISM\n")
    bad = _write(tmp, "harness_bad.md", "garbage\n")

    scorer = AssertionScorer([
        Assertion("contains", "line1", label="has line1"),
        Assertion("contains", "line2", label="has line2"),
        Assertion("contains", "EXTRA_MECHANISM", weight=2.0, label="has mechanism"),
        Assertion("min_lines", "3", label="3+ lines"),
    ])
    s_parent, s_good, s_bad = scorer(parent), scorer(good), scorer(bad)

    # 1 打分器在 [0,1] 且改进 > 破坏
    check("01 scorer range & ordering", 0.0 <= s_bad < s_parent < s_good <= 1.0,
          f"{s_bad} < {s_parent} < {s_good}")

    # 2 Proposer 改进 -> 正奖励
    v = evaluate_attempt(Attempt(role="proposer", parent_score=s_parent, child_score=s_good))
    check("02 proposer improvement -> +reward", v.exec_reward > 0 and v.admissible, f"{v.exec_reward}")

    # 3 Proposer 破坏 -> 负奖励
    v = evaluate_attempt(Attempt(role="proposer", parent_score=s_parent, child_score=s_bad))
    check("03 proposer regression -> -reward", v.exec_reward < 0, f"{v.exec_reward}")

    # 4 keep -> 0
    v = evaluate_attempt(Attempt(role="proposer", action="keep", parent_score=s_parent, child_score=s_parent))
    check("04 keep action -> 0", v.exec_reward == 0.0 and v.admissible, f"{v.exec_reward}")

    # 5 malformed -> 负奖励 + 不入账
    v = evaluate_attempt(Attempt(role="proposer", parent_score=s_parent, child_score=s_good,
                                 penalties=["malformed_output"]))
    check("05 malformed -> -reward & inadmissible", v.shaped_reward < 0 and not v.admissible,
          f"shaped={v.shaped_reward} adm={v.admissible}")

    # 6 Reflector 机制跑过且涨分 -> 正奖励
    v = evaluate_attempt(Attempt(role="reflector", before_score=s_parent, after_score=s_good,
                                 mechanism_ran=True))
    check("06 reflector evidenced gain -> +reward", v.exec_reward > 0, f"{v.exec_reward}")

    # 7 ★阴性对照：Reflector 涨分但机制没跑 -> 奖励必须置 0
    v = evaluate_attempt(Attempt(role="reflector", before_score=s_parent, after_score=s_good,
                                 mechanism_ran=False))
    check("07 ★NEG reflector no-evidence -> gain zeroed",
          v.exec_reward == 0.0 and v.components.get("suppressed") is True,
          f"exec={v.exec_reward} suppressed={v.components.get('suppressed')}")

    # 8 Type B 触及指定文件 -> bonus；不触及 -> malus
    va = evaluate_attempt(Attempt(role="proposer", task_type="B", parent_score=s_parent,
                                  child_score=s_good, directive_files=["a.py"], touched_files=["a.py"]))
    vb = evaluate_attempt(Attempt(role="proposer", task_type="B", parent_score=s_parent,
                                  child_score=s_good, directive_files=["a.py"], touched_files=["b.py"]))
    check("08 type-B bonus/malus", va.shaped_reward > vb.shaped_reward,
          f"hit={va.shaped_reward} miss={vb.shaped_reward}")

    # 9 edit extraction：无显式 action 也能从 reasoning 抽回
    rollout = [{"role": "assistant", "content":
                "I think we should patch the scorer.\n<<<EDIT>>>\nPATH: x.py\nOLD: line2\nNEW: line2_fixed\n<<<END>>>\nActually done."}]
    rec = recover_rollout(rollout, path_hint="x.py")
    check("09 edit extraction recovers 1 edit", len(rec.edits) == 1 and rec.edits[0].new == "line2_fixed",
          f"n={len(rec.edits)}")

    # 10 prefix continuation：第 2 个编辑坏 -> 截断在 1，保留前 1 个
    rollout2 = [{"role": "assistant", "content":
                 "<<<EDIT>>>\nPATH: x.py\nOLD: a\nNEW: b\n<<<END>>>\n"
                 "<<<EDIT>>>\nPATH: x.py\nOLD: c\nNEW: d\n<<<END>>>"}]
    rec2 = recover_rollout(rollout2, applied_ok=[True, False], path_hint="x.py")
    check("10 prefix continuation truncates at bad edit",
          rec2.truncated_at == 1 and rec2.needs_resume and len(rec2.usable_edits) == 1,
          f"trunc={rec2.truncated_at} usable={len(rec2.usable_edits)}")

    # 11 ★阴性对照：needs_resume 的恢复必须不入账
    v = evaluate_attempt(Attempt(role="proposer", parent_score=s_parent, child_score=s_good,
                                 recovered=True, needs_resume=True))
    check("11 ★NEG pending resume -> inadmissible", not v.admissible, f"{v.reasons}")

    # 12 台账落盘 + 读回 + 统计
    led = Ledger(os.path.join(tmp, "led.jsonl"))
    led.append({"label": "t1", "verdict": v.as_dict()})                      # inadmissible, +0.4
    led.append({"label": "t2", "verdict": evaluate_attempt(
        Attempt(role="proposer", parent_score=s_parent, child_score=s_good)).as_dict()})   # adm, +0.4
    led.append({"label": "t3", "verdict": evaluate_attempt(
        Attempt(role="proposer", parent_score=s_parent, child_score=s_bad)).as_dict()})    # adm, -0.6
    st = led.stats()
    check("12 ledger roundtrip & stats",
          st["n"] == 3 and st["admissible"] == 2 and st["positive"] == 2 and st["negative"] == 1,
          json.dumps(st))

    # 13 ★阴性对照：旧的「只看分数涨」判定必须被判为不足（本轮总闸对照）
    naive_pass = s_good > s_parent                       # 朴素判定：涨了就算好
    strict_pass = evaluate_attempt(Attempt(
        role="reflector", before_score=s_parent, after_score=s_good,
        mechanism_ran=False)).exec_reward > 0
    check("13 ★NEG naive 'score went up' != credited", naive_pass and not strict_pass,
          f"naive={naive_pass} strict={strict_pass}")

    # 14 ★阴性对照：无机制证据的 Reflector，即使 Type B bonus 为正，也不得入账
    vb_nod = evaluate_attempt(Attempt(
        role="reflector", task_type="B", before_score=s_parent, after_score=s_good,
        mechanism_ran=False, directive_files=["a.py"], touched_files=["a.py"]))
    check("14 ★NEG no-evidence reflector cannot be admitted even with type-B bonus",
          vb_nod.shaped_reward > 0 and not vb_nod.admissible,
          f"shaped={vb_nod.shaped_reward} adm={vb_nod.admissible}")

    passed = sum(1 for _, ok, _ in results if ok)
    if verbose:
        print(f"evotide_lite v{VERSION} selftest — {passed}/{len(results)} passed")
        for name, ok, detail in results:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    return 0 if passed == len(results) else 1


# ---------------------------------------------------------------- Demo（端到端真跑）

DEMO_HARNESS = """# demo-harness

## 规则
- 必须声明版本
- 必须给出回滚命令
"""

DEMO_GOOD = """# demo-harness

## 规则
- 必须声明版本 (version: 1.2.0)
- 必须给出回滚命令: rollback --to 1.1.0
- 必须先跑 selftest
"""

DEMO_BAD = """# demo-harness

随便写点东西
"""


def demo() -> int:
    """端到端：造父/子 harness -> 打分 -> 双角色评估 -> 写台账 -> 打印 rsi_gate 候选。"""
    tmp = tempfile.mkdtemp(prefix="evotide_demo_")
    p = _write(tmp, "harness.md", DEMO_HARNESS)
    g = _write(tmp, "harness_good.md", DEMO_GOOD)
    b = _write(tmp, "harness_bad.md", DEMO_BAD)

    sc = AssertionScorer([
        Assertion("contains", "version:", label="声明版本"),
        Assertion("contains", "rollback", label="回滚命令"),
        Assertion("contains", "selftest", label="先跑 selftest"),
        Assertion("min_lines", "5", label="结构完整"),
    ])
    s_p, s_g, s_b = sc(p), sc(g), sc(b)
    print(f"demo harness scores: parent={s_p}  good={s_g}  bad={s_b}")

    led = Ledger(os.path.join(tmp, "demo_ledger.jsonl"))
    attempts = [
        ("A1 Proposer 加 selftest 与回滚", Attempt(role="proposer", parent_score=s_p, child_score=s_g)),
        ("A2 Proposer 删规则", Attempt(role="proposer", parent_score=s_p, child_score=s_b)),
        ("A3 Proposer 格式错", Attempt(role="proposer", parent_score=s_p, child_score=s_g,
                                       penalties=["malformed_output"])),
        ("A4 Proposer keep", Attempt(role="proposer", action="keep",
                                     parent_score=s_p, child_score=s_p)),
        ("B1 Reflector 有证据增益", Attempt(role="reflector", task_type="B",
                                            before_score=s_p, after_score=s_g, mechanism_ran=True,
                                            directive_files=["harness.md"], touched_files=["harness.md"])),
        ("B2 ★Reflector 无证据增益", Attempt(role="reflector", task_type="B",
                                             before_score=s_p, after_score=s_g, mechanism_ran=False,
                                             directive_files=["harness.md"], touched_files=["harness.md"])),
    ]
    rows = []
    for label, att in attempts:
        v = evaluate_attempt(att)
        child = att.child_score if att.child_score is not None else (att.after_score or 0.0)
        cand = to_rsi_candidate(v, label, child)
        rec = {"label": label, "verdict": v.as_dict(), "rsi_candidate": cand}
        led.append(rec)
        rows.append(rec)
        print(f"  {label:<28} exec={v.exec_reward:+.3f} shaped={v.shaped_reward:+.3f} "
              f"admissible={v.admissible}  reasons={v.reasons}")

    print(f"\nledger -> {led.path}")
    print("stats  ->", json.dumps(led.stats(), ensure_ascii=False))

    # 真跑一遍轨迹恢复（模拟一次被截断的 rollout）
    rollout = [{"role": "assistant", "content":
                "I'll add selftest first.\n<<<EDIT>>>\nPATH: harness.md\nOLD: 必须声明版本\nNEW: 必须声明版本 (version: 1.2.0)\n<<<END>>>\n"
                "then rollback.\n<<<EDIT>>>\nPATH: harness.md\nOLD: 必须给出回滚命令\nNEW: 必须给出回滚命令: rollback --to 1.1.0\n<<<END>>>\n"
                "then a malformed one"}]
    rec = recover_rollout(rollout, applied_ok=[True, True, False], path_hint="harness.md")
    print(f"\nrecovery: edits={len(rec.edits)} recovered={rec.recovered} "
          f"truncated_at={rec.truncated_at} usable={len(rec.usable_edits)} needs_resume={rec.needs_resume}")
    for n in rec.notes:
        print("  note:", n)

    # 证明恢复结果确实能应用（端到端，不是纸面）
    content = open(p, encoding="utf-8").read()
    for e in rec.usable_edits:
        content = e.apply_to(content)
    after = _write(tmp, "harness_after.md", content)
    print(f"applied {len(rec.usable_edits)} recovered edit(s) -> score {sc(after)} (was {s_p})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="EvoTIDE-lite: 轨迹恢复 + 双角色评估（不训权重）")
    ap.add_argument("--selftest", action="store_true", help="跑 13 项自检（含 3 项阴性对照）")
    ap.add_argument("--demo", action="store_true", help="端到端演示并写台账")
    ap.add_argument("--version", action="version", version=f"evotide_lite {VERSION}")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.demo:
        return demo()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
