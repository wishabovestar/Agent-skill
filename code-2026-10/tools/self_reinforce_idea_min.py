#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
self_reinforce_idea_min.py — 六阶段 critic/refine 最小实现（零成本，不接实验执行）

设计来源
--------
1) 本机 skill `self-reinforcement` 的 Phase 1..6 骨架
   (数学分析 → 需求提炼 → 搜索 → 评估筛选 → 自我批评 → 迭代实施/过闸)
2) ScientistTwo (arXiv 2609.19644) 的 Idea Critic / Rebuttal / Meta-Review 闭环
3) rsi_gate.py 的阶梯铁律：adopt → in_domain_heldout → ood → cross_model，
   held-out 任一回退即否决（标量奖励看不见「拿已解换新解」）

本实现只做 idea → critic → refine → 回灌，**不做实验执行**，不训权重：
所有推理走本机 Ollama，零 API 成本。

六阶段（与 skill 的 Phase 一一对应）
-----------------------------------
S1 PROPOSE   ≈ Phase 1 数学分析      : 由种子问题产出结构化 idea v1
S2 REQUIRE   ≈ Phase 2 需求提炼      : 从 v1 抽出「待加固点」清单（本地，不检索）
S3 CRITIQUE  ≈ Phase 4 评估筛选      : 四维 rubric 打分 + 问题清单（critic A）
S4 REFINE    ≈ Phase 5 自我批评→改稿 : 逐条 issue → fix，产出 v2
S5 VERIFY    ≈ Phase 5 交叉审查      : held-out critic B（**不同模型家族**）独立打分
                                        + 扰动探针 + v1 重复打分得噪声地板
S6 ADMIT     ≈ Phase 6 迭代实施      : 过 rsi_gate，阶梯+集合契约判决，落台账

严格区分两种失败
----------------
* 结构性失败（输出非法 JSON / 字段缺失）→ 按 EvoTIDE 规则：该轮 Δ 不可归因，
  Δ 置 0、admissible=False，但仍然记账（不许静默丢弃）。
* 能力性失败（分数低）→ 正常过闸，由闸判拒。

用法
----
  python self_reinforce_idea_min.py --selftest
  python self_reinforce_idea_min.py --seed "你的研究种子问题" --rounds 2
  python self_reinforce_idea_min.py --seed ... --critic qwen2.5:7b --judge qwen3:8b
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
LEDGER_DIR = Path(r"D:/hermes/analysis/reinforcement_logs/idea_refine")
GATE_DIR = Path(r"D:/hermes/analysis")

DIMS = ("novelty", "soundness", "testability", "scope_risk")
DIM_CN = {"novelty": "新颖性", "soundness": "机制自洽", "testability": "可测性", "scope_risk": "范围风险"}
FIXED_SOLVED_THRESHOLD = 3.0   # 单维 ≥3/5 视为「v1 已解出的性质」，v2 不许丢


# ──────────────────────────────────────────────────────────────
# LLM 后端（本机 Ollama；--selftest 用 Stub）
# ──────────────────────────────────────────────────────────────
class Ollama:
    def __init__(self, model: str, temperature: float = 0.4, num_predict: int = 700, timeout: int = 240):
        self.model = model
        self.temperature = temperature
        self.num_predict = num_predict
        self.timeout = timeout
        self.calls = 0

    def chat(self, system: str, user: str, temp: float | None = None,
             json_mode: bool = False) -> str:
        if "qwen3" in self.model.lower() and "/no_think" not in system:
            system = system + " /no_think"      # Qwen3 软开关：否则 thinking 吃光 num_predict
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": self.temperature if temp is None else temp,
                        "num_predict": self.num_predict},
        }
        if json_mode:                      # Ollama 结构化输出：硬保证合法 JSON
            payload["format"] = "json"
        req = urllib.request.Request(
            f"{OLLAMA}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            out = json.loads(r.read().decode("utf-8", "replace"))
        self.calls += 1
        return (out.get("message") or {}).get("content", "") or ""


class Stub:
    """离线自检后端：按调用序返回预置 JSON，用于验证流程与闸接线（不验质量）。"""

    def __init__(self):
        self.calls = 0

    def chat(self, system: str, user: str, **kw) -> str:
        self.calls += 1
        if "JSON_SCORE" in user:                       # 打分调用
            base = 12.0 if "v1" in user else 16.0
            if "扰动" in user:
                base -= 2.0
            return json.dumps({
                "JSON_SCORE": True,
                "novelty": base / 4, "soundness": base / 4,
                "testability": base / 4, "scope_risk": base / 4,
                "issues": ["stub-issue-1", "stub-issue-2"],
                "note": "stub",
            }, ensure_ascii=False)
        if "JSON_IDEA" in user:
            return json.dumps({
                "JSON_IDEA": True,
                "title": "stub idea",
                "mechanism": "stub mechanism",
                "why_new": "stub",
                "metric": "stub metric",
                "risks": ["stub-risk"],
                "issues": ["i1", "i2"],
                "fixes": [{"issue": "i1", "fix": "f1", "changed": True}],
            }, ensure_ascii=False)
        return "ok"


# ──────────────────────────────────────────────────────────────
# JSON 抽取（模型可能包 ```json 或前置说明）
# ──────────────────────────────────────────────────────────────
def extract_json(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    body = m.group(1) if m else None
    if body is None:
        start = text.find("{")
        if start < 0:
            return None
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    body = text[start:i + 1]
                    break
    if not body:
        return None
    try:
        return json.loads(body)
    except Exception:
        try:
            return json.loads(body.replace("\n", " ").replace(",}", "}"))
        except Exception:
            return None


def rubric_total(d: dict) -> float:
    """四维各 0-5 → 总分 0-20；缺维按 0 计（fail-closed）。"""
    tot = 0.0
    for k in DIMS:
        v = d.get(k, 0)
        try:
            v = float(v)
        except Exception:
            v = 0.0
        tot += max(0.0, min(5.0, v))
    return tot


# ──────────────────────────────────────────────────────────────
# 六个阶段
# ──────────────────────────────────────────────────────────────
SYS_PROPOSE = (
    "你是算法研究员。输出必须是严格 JSON，不要任何解释文字。"
    "字段：title, mechanism, why_new, metric, risks(数组), assumptions(数组)。"
)

SYS_REQUIRE = (
    "你是研究组长。任务是把一个想法拆成『必须加固的点』。"
    "输出严格 JSON：{\"requirements\":[{\"id\":\"r1\",\"text\":\"...\",\"why\":\"...\"}]}，3-5 条，"
    "只针对本想法内部弱点，不要求做外部文献检索。"
)

SYS_CRITIQUE = (
    "你是苛刻的审稿人。用四维 rubric 打分，每维 0-5（0=不可用，5=顶会级）："
    "novelty(新颖性), soundness(机制自洽/因果链), testability(可否用现有仪器或数据检验), "
    "scope_risk(范围风险，5=风险最低)。"
    "JSON_SCORE 模式下只输出：{\"JSON_SCORE\":true,\"novelty\":x,\"soundness\":x,"
    "\"testability\":x,\"scope_risk\":x,\"issues\":[\"具体缺陷，最多4条\"],\"one_line\":\"一句话判决\"}"
)

SYS_REFINE = (
    "你是研究组长。按审稿意见逐条改稿，禁止回避任何一条 issue。"
    "输出严格 JSON：{\"title\",\"mechanism\",\"why_new\",\"metric\",\"risks\","
    "\"fixes\":[{\"issue\":\"原 issue 原文\",\"fix\":\"怎么改的\",\"changed\":true|false}]}"
)

SYS_JUDGE = (
    "你是独立评审（未参与改稿）。只按自己的判断给四维 0-5 分，不看别人给过的分。"
    "JSON_SCORE 模式下只输出：{\"JSON_SCORE\":true,\"novelty\":x,\"soundness\":x,"
    "\"testability\":x,\"scope_risk\":x,\"verdict\":\"accept|borderline|reject\"}"
)


def s1_propose(llm, seed: str) -> tuple[dict, str]:
    raw = llm.chat(SYS_PROPOSE, f"种子问题：{seed}\n请给出一个新机制型想法（不要求实验）。", json_mode=True)
    d = extract_json(raw)
    ok = bool(d and d.get("title") and d.get("mechanism"))
    return (d or {"title": "(parse_fail)", "mechanism": raw[:400], "raw": raw, "structured": False}), raw


def s2_require(llm, seed: str, idea: dict) -> dict:
    raw = llm.chat(SYS_REQUIRE, f"种子：{seed}\n想法：{json.dumps(idea, ensure_ascii=False)[:1200]}", json_mode=True)
    d = extract_json(raw) or {}
    reqs = d.get("requirements") or []
    return {"requirements": reqs if isinstance(reqs, list) else [], "raw": raw}


def s3_critique(llm, seed: str, idea: dict, reqs: dict, tag: str) -> dict:
    user = (
        "JSON_SCORE\n"
        f"种子：{seed}\n"
        f"待评对象（{tag}）：{json.dumps(idea, ensure_ascii=False)[:1600]}\n"
        f"研究组长提出的待加固点：{json.dumps(reqs.get('requirements', []), ensure_ascii=False)[:600]}\n"
        "请打分并列出最多 4 条具体缺陷。"
    )
    raw = llm.chat(SYS_CRITIQUE, user, json_mode=True)
    d = extract_json(raw)
    if not d or any(k not in d for k in DIMS):
        # 结构性失败：有界重试（最多再 2 次，temp=0 + 强制 JSON），仍失败才判死
        for _ in range(2):
            try:
                raw2 = llm.chat(SYS_CRITIQUE, "只输出 JSON，第一个字符必须是 {。" + user,
                                temp=0.0, json_mode=True)
            except TypeError:                  # Stub 不接受 temp
                raw2 = llm.chat(SYS_CRITIQUE, "只输出 JSON。" + user)
            d2 = extract_json(raw2)
            if d2 and all(k in d2 for k in DIMS):
                d, raw = d2, raw2
                break
    if not d or any(k not in d for k in DIMS):
        return {"structured": False, "total": 0.0, "issues": [], "raw": raw}
    return {"structured": True, "total": rubric_total(d), "dims": {k: d.get(k) for k in DIMS},
            "issues": d.get("issues") or [], "one_line": d.get("one_line", ""), "raw": raw}


def s4_refine(llm, seed: str, idea: dict, crit: dict) -> tuple[dict, str]:
    user = (
        f"种子：{seed}\n原稿：{json.dumps(idea, ensure_ascii=False)[:1400]}\n"
        f"审稿意见：{json.dumps(crit.get('issues', []), ensure_ascii=False)}\n"
        "逐条给出改动，不许把已有性质改没。"
    )
    raw = llm.chat(SYS_REFINE, user, json_mode=True)
    d = extract_json(raw)
    ok = bool(d and d.get("mechanism"))
    return (d or {"title": idea.get("title"), "mechanism": raw[:400], "structured": False}), raw


def s5_verify(llm_a, llm_b, seed: str, v1: dict, v2: dict, crit1: dict) -> dict:
    """held-out 阶梯：adopt / 扰动探针 / 跨模型 + v1 重复打分给噪声地板。"""
    a_v2 = s3_critique(llm_a, seed, v2, {"requirements": []}, "refined-v2")
    # 噪声地板：v1 重复打分一次（锚点自身一致度）
    a_v1_rep = s3_critique(llm_a, seed, v1, {"requirements": []}, "v1-repeat")
    # 扰动探针（in_domain_heldout）
    perturb_seed = seed + "（附加约束：把成本、尺寸、时间三项约束各加严一倍，同一机制是否仍成立）"
    p1 = s3_critique(llm_a, perturb_seed, v1, {"requirements": []}, "v1-perturb")
    p2 = s3_critique(llm_a, perturb_seed, v2, {"requirements": []}, "v2-perturb")
    # 跨模型（held-out judge，不同模型家族）
    b1 = s3_critique(llm_b, seed, v1, {"requirements": []}, "v1-cross-model")
    b2 = s3_critique(llm_b, seed, v2, {"requirements": []}, "v2-cross-model")
    return {
        "a_v1": crit1.get("total", 0.0),
        "a_v1_dims": crit1.get("dims") or {},
        "a_v1_repeat": a_v1_rep.get("total", 0.0),
        "a_v2": a_v2.get("total", 0.0),
        "a_v2_dims": a_v2.get("dims") or {},
        "perturb_v1": p1.get("total", 0.0),
        "perturb_v2": p2.get("total", 0.0),
        "x_v1": b1.get("total", 0.0),
        "x_v2": b2.get("total", 0.0),
        "structured_all": all(x.get("structured", False) for x in (a_v2, a_v1_rep, p1, p2, b1, b2)),
        "verdict_b": b2.get("one_line", ""),
        "issues_v2": a_v2.get("issues", []),
    }


def _dim(d: dict, k: str) -> float:
    try:
        return float((d or {}).get(k, 0) or 0)
    except Exception:
        return 0.0


def s6_admit(name: str, v1_dims: dict, v2_dims: dict, sc: dict, structured_ok: bool,
             best_so_far: float | None, diff_bits: dict | None = None) -> dict:
    """过 rsi_gate；导入失败时退回「下界规则」并显式标注 gate_source。

    注意：集合契约比的是【critic 打出的维度分】，不是 idea 字典本身——
    idea 字典里没有 dims，拿错对象会让 parent/child 恒为空、闸恒拒（已踩）。
    """
    solved_p = {k for k in DIMS if _dim(v1_dims, k) >= FIXED_SOLVED_THRESHOLD}
    solved_c = {k for k in DIMS if _dim(v2_dims, k) >= FIXED_SOLVED_THRESHOLD}


    d_adopt = sc["a_v2"] - sc["a_v1"]
    d_pert = sc["perturb_v2"] - sc["perturb_v1"]
    d_cross = sc["x_v2"] - sc["x_v1"]
    if not structured_ok:
        d_adopt = d_pert = d_cross = 0.0     # EvoTIDE 规则：结构性失败 ⇒ 增益不可归因

    diff = json.dumps(diff_bits or {}, ensure_ascii=False)[:1200]
    out = {
        "name": name, "d_adopt": d_adopt, "d_perturb": d_pert, "d_cross": d_cross,
        "parent_solved": sorted(solved_p), "child_solved": sorted(solved_c),
        "gap": len(solved_p - solved_c), "structured": structured_ok,
        "gained": sorted(solved_c - solved_p), "lost": sorted(solved_p - solved_c),
        "parent_dims": {k: _dim(v1_dims, k) for k in DIMS},
        "child_dims": {k: _dim(v2_dims, k) for k in DIMS},
    }
    try:
        sys.path.insert(0, str(GATE_DIR))
        from rsi_gate import Candidate, DualReport, GateConfig, evaluate
        cand = Candidate(
            name=name, diff=diff,
            parent_solved=solved_p, child_solved=solved_c,
            score=sc["a_v2"], d_score=d_adopt, d_cost=0.0,
            resolved=structured_ok, verified=structured_ok,
        )
        dual = DualReport(
            scores={"adopt": sc["a_v2"]},
            deltas={"adopt": d_adopt, "in_domain_heldout": d_pert, "cross_model": d_cross},
        )
        verdict = evaluate(
            cand, GateConfig(), best_so_far=best_so_far,
            baseline_scores=[sc["a_v1"], sc["a_v1_repeat"]], dual=dual,
        )
        out.update(gate_source="rsi_gate", admit=bool(verdict.get("admit")),
                   reasons=verdict.get("reasons", []))
    except Exception as e:                     # 闸不可用 ⇒ 降级但不伪装通过
        lb = d_adopt - 1.645 * (abs(sc["a_v1"] - sc["a_v1_repeat"]) / 2 ** 0.5)
        ok = (lb >= -0.02 * 20) and d_pert >= 0 and d_cross >= 0 and not (solved_p - solved_c) and structured_ok
        out.update(gate_source=f"lower_bound_fallback({type(e).__name__})", admit=bool(ok),
                   reasons=[f"LB Δ={d_adopt:.2f} 下界={lb:.2f}", f"perturb={d_pert:+.2f}",
                            f"cross={d_cross:+.2f}", f"lost={sorted(solved_p - solved_c)}"])
    return out


# ──────────────────────────────────────────────────────────────
# 主循环
# ──────────────────────────────────────────────────────────────
def run(seed: str, rounds: int, critic_model: str, judge_model: str, stub: bool = False) -> dict:
    llm_a = Stub() if stub else Ollama(critic_model, temperature=0.4)
    llm_b = Stub() if stub else Ollama(judge_model, temperature=0.2)
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ledger = LEDGER_DIR / f"idea_refine_{stamp}.jsonl"
    best = None
    records = []

    idea = None
    for r in range(1, rounds + 1):
        t0 = time.time()
        if idea is None:
            v1, raw1 = s1_propose(llm_a, seed)
        else:                                   # 回灌：上一轮 v2 当新 v1
            v1, raw1 = idea, json.dumps(idea, ensure_ascii=False)
        reqs = s2_require(llm_a, seed, v1)
        crit1 = s3_critique(llm_a, seed, v1, reqs, "v1")
        v2, raw2 = s4_refine(llm_a, seed, v1, crit1)
        sc = s5_verify(llm_a, llm_b, seed, v1, v2, crit1)
        ok = bool(v1.get("structured", True)) and bool(v2.get("structured", True)) and sc["structured_all"]
        if not ok and not stub:
            ok = bool(extract_json(raw1)) and bool(extract_json(raw2)) and sc["structured_all"]
        verdict = s6_admit(f"idea_refine_r{r}", sc.get("a_v1_dims") or {}, sc.get("a_v2_dims") or {},
                           sc, ok, best,
                           {"v1": v1.get("mechanism", "")[:400], "v2": v2.get("mechanism", "")[:400]})
        rec = {
            "ts": datetime.now().isoformat(timespec="seconds"), "round": r, "seed": seed,
            "score_v1": sc["a_v1"], "score_v1_repeat": sc["a_v1_repeat"], "score_v2": sc["a_v2"],
            "perturb": [sc["perturb_v1"], sc["perturb_v2"]],
            "cross_model": [sc["x_v1"], sc["x_v2"]],
            "issues_v1": crit1.get("issues", []), "issues_v2": sc["issues_v2"],
            "verdict": verdict, "elapsed_s": round(time.time() - t0, 1),
            "calls": {"critic": llm_a.calls, "judge": llm_b.calls},
        }
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        records.append(rec)
        if verdict["admit"]:
            best = sc["a_v2"]
            idea = v2                           # 只把过闸的版本回灌（回灌闸）
        else:
            idea = v2 if sc["a_v2"] > sc["a_v1"] else v1

    return {"ledger": str(ledger), "records": records,
            "calls": {"critic": llm_a.calls, "judge": llm_b.calls}}


def print_report(res: dict) -> None:
    print("=" * 78)
    print(f"台账: {res['ledger']}")
    print(f"调用: critic={res['calls']['critic']} judge={res['calls']['judge']} (本机 Ollama，成本 0)")
    print("-" * 78)
    print(f"{'轮':<3}{'S(v1)':>7}{'S(v1)重测':>10}{'S(v2)':>7}{'Δadopt':>8}"
          f"{'Δ扰动':>8}{'Δ跨模型':>9}{'丢性质':>7}{'判决':>8}")
    for r in res["records"]:
        v = r["verdict"]
        print(f"{r['round']:<3}{r['score_v1']:>7.1f}{r['score_v1_repeat']:>10.1f}{r['score_v2']:>7.1f}"
              f"{v['d_adopt']:>+8.2f}{v['d_perturb']:>+8.2f}{v['d_cross']:>+9.2f}{v['gap']:>7}"
              f"{('ADMIT' if v['admit'] else 'REJECT'):>8}")
    print("-" * 78)
    for r in res["records"]:
        print(f"轮 {r['round']} 判决依据:")
        for x in r["verdict"]["reasons"]:
            print("   -", x)
        print(f"   issues(v1)={r['issues_v1'][:3]}")


def selftest() -> int:
    """离线自检：验证六阶段串联、JSON 抽取、闸接线、结构性失败置零。"""
    fails = []
    # 1) JSON 抽取
    assert extract_json('前言```json\n{"a":1}\n```后记') == {"a": 1}
    assert extract_json('{"a":{"b":2}} tail') == {"a": {"b": 2}}
    assert extract_json("no json") is None
    # 2) rubric 边界
    assert rubric_total({"novelty": 5, "soundness": 5, "testability": 5, "scope_risk": 5}) == 20
    assert rubric_total({"novelty": 99, "soundness": -3}) == 5  # clamp + 缺维计 0
    # 3) 全流程（stub）
    res = run("自检种子：用感知哈希检测极片涂布条纹", rounds=2, critic_model="stub", judge_model="stub", stub=True)
    if len(res["records"]) != 2:
        fails.append("轮数不对")
    r0 = res["records"][0]
    if r0["score_v2"] <= r0["score_v1"]:
        fails.append("stub 下 v2 应高于 v1")
    if r0["verdict"]["gate_source"] != "rsi_gate":
        fails.append(f"闸未接上: {r0['verdict']['gate_source']}")
    if not os.path.exists(res["ledger"]):
        fails.append("台账未落盘")
    # 4) 结构性失败 ⇒ Δ 置零 + 拒
    sc = {"a_v1": 10, "a_v1_repeat": 10, "a_v2": 18, "perturb_v1": 8,
          "perturb_v2": 16, "x_v1": 9, "x_v2": 17, "structured_all": False}
    v = s6_admit("t", {"novelty": 4}, {"novelty": 4}, sc, False, None)
    if v["d_adopt"] != 0 or abs(v["d_cross"]) > 1e-9 or v["admit"]:
        fails.append("结构性失败未置零/未拒")
    # 5) 丢性质 ⇒ 拒（集合契约）
    sc2 = dict(sc, structured_all=True)
    v2 = s6_admit("t2", {"novelty": 4, "soundness": 4},
                  {"novelty": 4}, sc2, True, None)
    if v2["admit"] and v2["gap"] > 0:
        fails.append("丢性质仍被放行")
    # 6) 不丢性质且四档不回退 ⇒ 必须放行（防「闸恒拒」假阴性）
    v3 = s6_admit("t3", {"novelty": 4, "soundness": 4},
                  {"novelty": 4, "soundness": 4, "testability": 4}, sc2, True, None)
    if not v3["admit"]:
        fails.append("合法增益被拒（闸恒拒假阴性）: " + "; ".join(v3["reasons"]))
    print("selftest:", "PASS" if not fails else "FAIL " + "; ".join(fails))
    return 0 if not fails else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--critic", default="qwen2.5:7b")
    ap.add_argument("--judge", default="qwen3:8b")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.seed:
        ap.error("--seed 必填（或用 --selftest）")
    res = run(a.seed, a.rounds, a.critic, a.judge)
    print_report(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
