#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evotide_rsi_bridge.py — 把 EvoTIDE-lite 的评分回流接进 rsi_gate（self-reinforcement Phase 6 接受闸）

链路：
    harness 编辑 -> evotide_lite.evaluate_attempt -> Verdict
                -> verdict_to_candidate()          -> rsi_gate.Candidate
                -> rsi_gate.evaluate()             -> admit / reject + reasons

两个系统的语义映射（这是本文件的全部价值所在）：

| EvoTIDE-lite            | rsi_gate.Candidate | 说明 |
|:------------------------|:-------------------|:-----|
| exec_reward (ΔS)        | d_score            | 都是相对现任的分数增量 |
| child_score (绝对 S)    | score              | 供噪声地板 |
| admissible              | verified           | 证据是否可信 |
| admissible              | resolved           | 未过检查 = 未重测 ⇒ 闸默认拒（fail-closed）|
| 通过断言的集合          | child_solved       | 用于保留-扩展契约 |
| 父代通过断言的集合      | parent_solved      | 用于保留-扩展契约 |
| 0（不训权重）           | d_cost             | 只算推理成本 |

**关键设计**：EvoTIDE 的 S 是标量，rsi_gate 的保留-扩展契约要的是集合。
本桥接把"断言通过集合"当作任务解出集合 —— 这样"涨分但丢掉已解"的候选
会被铁律②（不许拿已解换新解）拦住，而标量分数看不出来。这是桥接真正的增量。

用法：
    python evotide_rsi_bridge.py --selftest   # 桥接自检（含 2 项阴性对照）
    python evotide_rsi_bridge.py --demo       # 端到端：编辑 -> EvoTIDE 评分 -> rsi_gate 判决
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, r"D:/hermes/analysis")

import evotide_lite as EL  # noqa: E402

try:
    import rsi_gate as RG  # noqa: E402
    _HAS_GATE = True
except Exception as exc:  # pragma: no cover
    _HAS_GATE = False
    _GATE_ERR = repr(exc)

BRIDGE_VERSION = "1.0.0"


# ---------------------------------------------------------------- 集合化打分

def solved_set(assertions: list[EL.Assertion], path: str) -> set[str]:
    """把一个 harness 通过的全部断言 label 当作"已解出任务集合"。"""
    try:
        content = open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return set()
    out = set()
    for a in assertions:
        try:
            if a.check(content, path):
                out.add(str(a))
        except Exception:
            pass
    return out


# ---------------------------------------------------------------- 语义映射

def verdict_to_candidate(v: EL.Verdict, label: str,
                         parent_solved: set[str], child_solved: set[str],
                         child_score: float, diff: str = "",
                         d_cost: float = 0.0):
    """
    Verdict -> rsi_gate.Candidate。

    注意 resolved 的取法：EvoTIDE 的 admissible=False 意味着"证据不足"（malformed /
    恢复未验证 / 无机制证据），而 rsi_gate 把 resolved=False 解读为"未重测"并直接拒。
    两边语义一致 —— 这是刻意对齐，不是巧合。
    """
    if not _HAS_GATE:
        raise RuntimeError(f"rsi_gate 不可用: {_GATE_ERR}")
    return RG.Candidate(
        name=label,
        diff=diff or f"evotide:{label}",
        parent_solved=set(parent_solved),
        child_solved=set(child_solved),
        score=float(child_score),
        resolved=bool(v.admissible),
        d_score=float(v.exec_reward),
        d_cost=float(d_cost),
        verified=bool(v.admissible),
    )


def run_gate(v: EL.Verdict, label: str, parent_solved: set[str],
             child_solved: set[str], child_score: float,
             parent_score: float, diff: str = "",
             baseline_scores: list[float] | None = None,
             d_cost: float = 0.0) -> dict:
    """跑 rsi_gate 全闸，返回判决 dict。"""
    cand = verdict_to_candidate(v, label, parent_solved, child_solved,
                               child_score, diff=diff, d_cost=d_cost)
    cfg = RG.GateConfig()
    # 噪声地板要绝对分数；best_so_far 用父代绝对分
    return RG.evaluate(cand, cfg,
                       best_so_far=parent_score if parent_score is not None else None,
                       baseline_scores=baseline_scores)


# ---------------------------------------------------------------- 自检

DEMO_PARENT = """# harness
- 必须声明版本
- 必须给出回滚命令
"""

DEMO_GOOD = """# harness
- 必须声明版本 version: 1.2.0
- 必须给出回滚命令 rollback --to 1.1.0
- 必须先跑 selftest
- 必须记录耗时
"""

# 「涨分但丢掉已解」的陷阱：多了两项，但删掉了"声明版本" —— 标量看是净涨，契约看是破坏
DEMO_TRADE = """# harness
- 必须给出回滚命令 rollback --to 1.1.0
- 必须先跑 selftest
- 必须记录耗时
- 必须有日志目录
"""


def selftest(verbose: bool = True) -> int:
    if not _HAS_GATE:
        print(f"rsi_gate unavailable: {_GATE_ERR}")
        return 2
    results: list[tuple[str, bool, str]] = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    tmp = tempfile.mkdtemp(prefix="evotide_bridge_")

    def w(n, c):
        p = os.path.join(tmp, n)
        open(p, "w", encoding="utf-8").write(c)
        return p

    p = w("h_parent.md", DEMO_PARENT)
    g = w("h_good.md", DEMO_GOOD)
    t = w("h_trade.md", DEMO_TRADE)

    assertions = [
        EL.Assertion("contains", "声明版本", label="版本声明"),
        EL.Assertion("contains", "回滚命令", label="回滚命令"),
        EL.Assertion("contains", "selftest", label="跑selftest"),
        EL.Assertion("contains", "耗时", label="记录耗时"),
        EL.Assertion("contains", "日志目录", label="日志目录"),
    ]
    sc = EL.AssertionScorer(assertions)
    s_p, s_g, s_t = sc(p), sc(g), sc(t)
    set_p, set_g, set_t = solved_set(assertions, p), solved_set(assertions, g), solved_set(assertions, t)

    # 前置：确认三个 harness 的关系符合设计意图
    check("00 fixtures as intended",
          s_p == 0.4 and set_p == {"版本声明", "回滚命令"}
          and s_t > s_p and "版本声明" not in set_t,
          f"sp={s_p} sg={s_g} st={s_t} | set_p={sorted(set_p)} set_t={sorted(set_t)}")

    # 1 真改进 -> EvoTIDE 正奖励 -> 闸通过
    v = EL.evaluate_attempt(EL.Attempt(role="proposer", parent_score=s_p, child_score=s_g))
    g1 = run_gate(v, "真改进", set_p, set_g, s_g, s_p, baseline_scores=[s_p] * 5)
    check("01 genuine improvement -> gate admit",
          v.exec_reward > 0 and g1["admit"] is True, f"r={v.exec_reward} admit={g1['admit']} {g1['reasons']}")

    # 2 真退化 -> 负奖励 -> 闸拒
    v = EL.evaluate_attempt(EL.Attempt(role="proposer", parent_score=s_g, child_score=s_p))
    g2 = run_gate(v, "真退化", set_g, set_p, s_p, s_g, baseline_scores=[s_g] * 5)
    check("02 regression -> gate reject",
          v.exec_reward < 0 and g2["admit"] is False, f"r={v.exec_reward} admit={g2['admit']}")

    # 3 ★阴性对照：涨分但丢掉已解 -> 铁律②（保留-扩展契约）必须拒
    v = EL.evaluate_attempt(EL.Attempt(role="proposer", parent_score=s_p, child_score=s_t))
    g3 = run_gate(v, "换解", set_p, set_t, s_t, s_p, baseline_scores=[s_p] * 5)
    check("03 ★NEG score up but lost solved task -> contract rejects",
          v.exec_reward > 0 and g3["admit"] is False,
          f"ΔS={v.exec_reward:+.3f} admit={g3['admit']} {g3['reasons']}")

    # 4 ★阴性对照：EvoTIDE inadmissible -> resolved=False -> 闸必须拒
    v = EL.evaluate_attempt(EL.Attempt(role="proposer", parent_score=s_p, child_score=s_g,
                                       penalties=["malformed_output"]))
    g4 = run_gate(v, "格式错", set_p, set_g, s_g, s_p, baseline_scores=[s_p] * 5)
    check("04 ★NEG evotide inadmissible -> gate rejects even if score up",
          not v.admissible and g4["admit"] is False,
          f"adm={v.admissible} gate_admit={g4['admit']}")

    # 5 无机制证据的 Reflector -> inadmissible -> 闸拒
    v = EL.evaluate_attempt(EL.Attempt(role="reflector", before_score=s_p, after_score=s_g,
                                       mechanism_ran=False))
    g5 = run_gate(v, "无证据", set_p, set_g, s_g, s_p, baseline_scores=[s_p] * 5)
    check("05 no-evidence reflector -> gate reject",
          g5["admit"] is False, f"admit={g5['admit']} {g5['reasons']}")

    # 6 有机制证据的 Reflector -> 闸通过
    v = EL.evaluate_attempt(EL.Attempt(role="reflector", before_score=s_p, after_score=s_g,
                                       mechanism_ran=True))
    g6 = run_gate(v, "有证据", set_p, set_g, s_g, s_p, baseline_scores=[s_p] * 5)
    check("06 evidenced reflector -> gate admit", g6["admit"] is True,
          f"admit={g6['admit']} {g6['reasons']}")

    # 7 字段映射完整性
    v = EL.evaluate_attempt(EL.Attempt(role="proposer", parent_score=s_p, child_score=s_g))
    c = verdict_to_candidate(v, "map", set_p, set_g, s_g)
    check("07 field mapping complete",
          c.d_score == v.exec_reward and c.verified is True and c.resolved is True
          and c.parent_solved == set_p and c.child_solved == set_g and c.score == s_g,
          f"d_score={c.d_score} verified={c.verified} resolved={c.resolved}")

    passed = sum(1 for _, ok, _ in results if ok)
    if verbose:
        print(f"evotide_rsi_bridge v{BRIDGE_VERSION} selftest — {passed}/{len(results)} passed")
        for name, ok, detail in results:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    return 0 if passed == len(results) else 1


# ---------------------------------------------------------------- 端到端 demo

def demo(persist: bool = False) -> int:
    if not _HAS_GATE:
        print(f"rsi_gate unavailable: {_GATE_ERR}")
        return 2
    print(f"rsi_gate loaded; evotide_lite v{EL.VERSION}")
    tmp = tempfile.mkdtemp(prefix="evotide_e2e_")

    def w(n, c):
        p = os.path.join(tmp, n)
        open(p, "w", encoding="utf-8").write(c)
        return p

    p = w("h_parent.md", DEMO_PARENT)
    g = w("h_good.md", DEMO_GOOD)
    t = w("h_trade.md", DEMO_TRADE)

    assertions = [
        EL.Assertion("contains", "声明版本", label="版本声明"),
        EL.Assertion("contains", "回滚命令", label="回滚命令"),
        EL.Assertion("contains", "selftest", label="跑selftest"),
        EL.Assertion("contains", "耗时", label="记录耗时"),
        EL.Assertion("contains", "日志目录", label="日志目录"),
    ]
    sc = EL.AssertionScorer(assertions)
    s_p, s_g, s_t = sc(p), sc(g), sc(t)
    set_p, set_g, set_t = solved_set(assertions, p), solved_set(assertions, g), solved_set(assertions, t)
    print(f"parent S={s_p} solved={sorted(set_p)}")
    print(f"good   S={s_g} solved={sorted(set_g)}")
    print(f"trade  S={s_t} solved={sorted(set_t)}   (分数更高，但丢了「版本声明」)\n")

    cases = [
        ("C1 真改进：补 selftest+耗时+日志", "proposer", s_p, s_g, set_p, set_g),
        ("C2 陷阱：涨分但删掉版本声明", "proposer", s_p, s_t, set_p, set_t),
    ]
    bad_path = os.path.join(tmp, "h_bad.md")
    open(bad_path, "w", encoding="utf-8").write("垃圾\n")
    s_b = sc(bad_path)
    set_b = solved_set(assertions, bad_path)
    cases.append(("C3 真退化：删光规则", "proposer", s_p, s_b, set_p, set_b))

    led = EL.Ledger(None if persist else os.path.join(tmp, "e2e_ledger.jsonl"))
    print(f"{'case':<34}{'ΔS':>8}{'adm':>7}{'gate':>7}  reasons")
    print("-" * 96)
    for label, role, before, after, sb, sa in cases:
        v = EL.evaluate_attempt(EL.Attempt(role=role, parent_score=before, child_score=after))
        gr = run_gate(v, label, sb, sa, after, before, baseline_scores=[before] * 5)
        admit = "ADMIT" if gr["admit"] else "REJECT"
        print(f"{label:<34}{v.exec_reward:>+8.3f}{str(v.admissible):>7}{admit:>7}  {gr['reasons'][:2]}")
        led.append({"label": label, "verdict": v.as_dict(),
                    "rsi_candidate": {k: (sorted(vv) if isinstance(vv, set) else vv)
                                      for k, vv in vars(verdict_to_candidate(
                                          v, label, sb, sa, after)).items()},
                    "gate": gr})

    print(f"\nledger -> {led.path}")
    print("stats  ->", json.dumps(led.stats(), ensure_ascii=False))
    print("\n结论：C1 通过；C2 分数更高但被保留-扩展契约拦下 —— 这正是标量 EvoTIDE 奖励")
    print("      单独使用时看不见的失败模式，必须靠 rsi_gate 的集合契约补上。")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="EvoTIDE-lite -> rsi_gate 桥接")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--persist", action="store_true", help="台账写入 EVOTIDE_LEDGER_DIR 而非临时目录")
    ap.add_argument("--version", action="version", version=f"evotide_rsi_bridge {BRIDGE_VERSION}")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.demo:
        return demo(persist=a.persist)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
