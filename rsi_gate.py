#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rsi_gate.py — 自我演化「接受闸」

依据（本机论文归档 PAPER_ARCHIVE_agent_memory_swarm_2026-10.md）：
  #63 RRSI (Google Research, arXiv:2609.24972)  非补偿性三闸：泄漏筛查 / 噪声地板 / 成本预算
  #64 DarwinX (Salesforce AI Research, arXiv:2608.07545)  保留-扩展契约：g(c)>0 且 R(c)<=delta
  #54 任务分数不能验证评估器   #19(铁律) 验收必须以 OOD 迁移为准

设计原则：
  * 纯函数，零依赖（仅 stdlib），不读不写任何生产文件。
  * 所有判据【非补偿性】：高分买不掉一个泄漏 / 一次回退。
  * 默认拒绝（fail-closed）：证据不足 = 不通过。

用法：
  from rsi_gate import evaluate, Candidate, GateConfig
  verdict = evaluate(candidate, cfg)
  print(verdict)          # {'admit': bool, 'reasons': [...], ...}

自检：  python rsi_gate.py        （跑内置 demo，不依赖外部文件）
"""
from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, field, asdict
from typing import Any


# ──────────────────────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────────────────────
@dataclass
class GateConfig:
    # 回退容差（#64 的 delta）：允许的"有界回退"总量，按任务数计
    regression_tolerance: float = 0.5
    # 噪声地板倍数：#65 的 delta 由基座重复评测的样本标准差估计
    noise_sigma_mult: float = 2.0
    # 成本-收益线性预算（#63 的 Ridge/L2 式）：ΔC <= beta0 + beta1*ΔS
    beta0: float = 0.10
    beta1: float = 0.50
    # 泄漏筛查关键词（示例集，按需扩展）
    leak_patterns: tuple = (
        r"\bTerminal-?Bench\b", r"\bSWE-?bench\b", r"\bWebArena\b", r"\bTerminalWorld\b",
        r"\bHarvey\b", r"\bJobBench\b", r"\bGDPval\b", r"\bAPEX-?Agents\b",
        r"\bEngDesign\b", r"\bFrontier-?Eng\b", r"\bKernelBench\b", r"\bAIME\b",
    )
    # "惰性机械"信号：只加不用的死代码/死配置
    inert_markers: tuple = ("dead_code", "unused_import", "no_op", "pass  # ", "TODO: noop")
    # ── 闸 ⑨ 评判器可靠性（设计清单 v1 第③条 ①）────────────────────
    #   依据：铁律 15（评判器/验证器必须能被自检；判别力 r_disc→0 即判据已死）
    #         铁律 46（报「与专家一致 X%」之前先报「专家与专家一致多少」= 锚点自身有噪声）
    #         铁律 10（独立验证者按【底层模型身份】计数，不按端点/角色）
    judge_min_anchor_n: int = 20        # 校准样本量下限
    judge_margin: float = 0.05          # ⭐ 评判器一致度必须【超过】锚点自身一致度至少这么多，否则它没带来信息
    judge_min_r_disc: float = 1e-6      # r_disc = std(判据在候选集上的打分)；<=0 ⇒ 判据已死
    judge_max_age_days: int = 180       # 上次更新时间上限（过期锚点不得准入）
    judge_min_independence: int = 1     # 独立验证者数量下限（按底层模型身份计）
    # ── 闸 ⑩ 上下游成对兼容（设计清单 v1 第③条 ②）────────────────
    require_pair_binding: bool = True   # 声明式：pairwise_compat 被调用时的默认严格度（此处仅作文档）
    # ── 总开关 ────────────────────────────────────────────────────
    #   False（默认）= 兼容模式：不提供 judge/pair 时【跳过】这两闸（旧调用方零影响）
    #   True        = 严格准入：不提供 judge/pair ⇒ 直接拒（fail-closed）⇒ 这两栏成为硬闸
    strict_admission: bool = False


# ──────────────────────────────────────────────────────────────
# MR6 · 翻转条件（reopen_if）
#   每条阈值/结论在什么情况下该被【推翻重来】。格式对齐元层 MR6 的要求：
#     观测量 / 阈值 / 翻转条件 / 如何复测。
#   没有这一块，本闸的结论会僵死 —— 阈值一旦不适用，没人知道该重开。
# ──────────────────────────────────────────────────────────────
reopen_if = {
    'noise_sigma_mult=2.0': dict(
        threshold='delta = 2.0 × stdev(基座重复评测)',
        flip='基座重复评测样本量 <5 且 stdev 被单个离群点支配时，delta 不可信 ⇒ 退回“极差/2”(noise_band 已内建该回退，但那是代码行为，不是判据已校准)',
        remeasure='把基座重复评测加到 ≥5 次，看 delta 是否稳定；不稳定则“噪声地板”这一结论不成立'),
    'regression_tolerance=0.5': dict(
        threshold='有界回退 R(c) <= 0.5（按任务数计）',
        flip='任务池 <20 时 0.5 个任务已占 >2.5%，绝对容差失去意义 ⇒ 应改比例制（本次校准已实测翻转通道：容差提到 999 ⇒ [C] 由 REJECT 变 ADMIT）',
        remeasure='python rsi_gate.py，看 [C] 是否仍 REJECT；若变 ADMIT ⇒ 容差过大'),
    'beta0/beta1=0.10/0.50': dict(
        threshold='ΔC <= beta0 + beta1·ΔS（线性成本-收益预算）',
        flip='成本量纲换了口径（如从 token 计费改为美元/墙钟）⇒ 线性系数必须重估',
        remeasure='拿一批已知“值/不值”的候选跑回归，看系数是否仍把两类分开'),
    'leak_patterns（关键词表）': dict(
        threshold='命中任一正则 ⇒ 拒（fail-closed）',
        flip='评测集改名而词表未更新 ⇒ 漏检；反之词表过宽 ⇒ 误杀通用改进（假阳性）',
        remeasure='用一条【确知泄漏】与一条【确知干净】的 diff 各跑一次，应分别 REJECT / ADMIT'),
    'dual_report(OOD / cross_model)': dict(
        threshold='任一 held-out 轴回退 ⇒ 拒（铁律 19）',
        flip='某个 held-out 轴自身的噪声带 > 待测效应量 ⇒ 该轴不该有否决权，应降为观察项',
        remeasure='同一候选用不同 held-out 划分跑 ≥3 次，看否决是否稳定'),
    'judge_margin=0.05 / judge_max_age_days=180': dict(
        threshold='评判器一致度 > 锚点自身一致度 + 0.05，且校准时间在 180 天内',
        flip='若某类评判器在【锚点自身也很吵】的域里长期跑不出这个 margin（如主观域 κ 天花板本就 0.6）⇒ 该 margin 不适用，应改为“按域给定 margin”而不是全局常数；反之若校准新鲜度与判决无相关性 ⇒ 180 天这一条只是仪式，应删',
        remeasure='拿一批【已知判对/判错】的评判器报告跑一遍，看这两条是否仍能分开两类；把 judge_max_age_days 设为极大值，看是否出现“过期锚点仍放行”'),
    'strict_admission（新两栏是否硬闸）': dict(
        threshold='True ⇒ 缺 judge_reliability / pairwise_compat 即拒',
        flip='若历史候选因缺栏被大面积拒（说明现存流程根本产不出这两栏）⇒ 先降为告警（WARN）并限期补齐，避免闸变成“全员拒”的死闸',
        remeasure='用一条【旧格式】（无 judge/pair）的已知合格候选跑 strict 与兼容两种模式，应分别 REJECT / ADMIT；若两者相同 ⇒ 开关没接上'),
}


# ──────────────────────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────────────────────
@dataclass
class Candidate:
    """一个候选 harness（或任意自我演化提案）。"""
    name: str
    diff: str = ""                              # 源码/配置 diff（供泄漏筛查）
    parent_solved: set = field(default_factory=set)   # 父代解出的任务集合 S(p)
    child_solved: set = field(default_factory=set)    # 候选解出的任务集合 S(c)
    score: float | None = None  # 候选的【绝对】分数（供噪声地板；与 delta 不同量纲，勿混用）
    resolved: bool = True   # 该候选是否已被【重测/preservation probe】确认（#64 双速设计）
    d_score: float = 0.0    # ΔS：相对现任的分数【增量】（供成本预算）
    d_cost: float = 0.0     # ΔC：相对成本变化（0.5 = 成本涨 50%）
    verified: bool = False  # 证据是否来自可信 verifier


# ──────────────────────────────────────────────────────────────
# 闸 ① 泄漏筛查（#63）—— 必须在【完整评估之前】跑
# ──────────────────────────────────────────────────────────────
def leak_screen(diff: str, cfg: GateConfig) -> tuple[bool, list[str]]:
    """拒绝【基准特定内容】与【惰性机械】。通用 prompt/工具描述改进仍有效。

    返回 (passed, reasons)。fail-closed：命中任一 = 不通过。
    """
    reasons: list[str] = []
    low = diff.lower()
    for pat in cfg.leak_patterns:
        if re.search(pat, diff, flags=re.IGNORECASE):
            reasons.append(f"leak: 命中基准特定标识 {pat!r}（把基准名/任务名写进 harness = 记忆而非能力）")
    for m in cfg.inert_markers:
        if m.lower() in low:
            reasons.append(f"inert: 命中惰性机械标记 {m!r}")
    # 任务特定数值/答案硬编码启发式：形如 "== 42" / "answer = 7"
    if re.search(r"\banswer\s*=\s*[-+]?\d+(\.\d+)?", low) or re.search(r"==\s*[-+]?\d{2,}\b", diff):
        reasons.append("leak: 疑似硬编码任务特定数值/答案")
    return (len(reasons) == 0), reasons


# ──────────────────────────────────────────────────────────────
# 闸 ② 噪声地板（#63）—— 先反复测【未改动的基座】
# ──────────────────────────────────────────────────────────────
def noise_band(baseline_scores: list[float], cfg: GateConfig) -> float:
    """估计经验噪声带 delta = mult * stdev(基座重复评测)。

    基座重复评测至少 3 次；样本太多取标准差，太少退回极差的一半。
    """
    if len(baseline_scores) < 2:
        raise ValueError("noise_band 需要基座的【重复】评测（>=2 次），否则无从谈噪声")
    if len(baseline_scores) >= 3:
        delta = statistics.stdev(baseline_scores)
    else:
        delta = (max(baseline_scores) - min(baseline_scores)) / 2.0
    if delta <= 0:                      # 完全无抖动时给一个下限，避免地板退化为 0
        delta = 1e-3
    return cfg.noise_sigma_mult * delta


def passes_noise_floor(score: float, best_so_far: float, delta: float) -> tuple[bool, str]:
    """Ŝ(H') >= S* - delta。防"连串小退步"一路走下坡。"""
    floor = best_so_far - delta
    ok = score >= floor
    return ok, f"noise_floor: {score:.4f} vs floor {floor:.4f} (S*={best_so_far:.4f}, delta={delta:.4f})"


# ──────────────────────────────────────────────────────────────
# 闸 ③ 成本预算（#63，Ridge/L2 式）
# ──────────────────────────────────────────────────────────────
def passes_cost_budget(d_score: float, d_cost: float, delta: float, cfg: GateConfig) -> tuple[bool, str]:
    """仅当增益超过噪声带时才要求 ΔC <= beta0 + beta1*ΔS（成本只能与收益成比例增长）。"""
    if d_score <= delta:
        # 增益没超过噪声 == 没有可信增益；此时不允许涨成本
        ok = d_cost <= 0.0
        return ok, f"cost_budget: 增益 {d_score:.4f} <= 噪声带 {delta:.4f}，判定无增益 → 成本必须不增（ΔC={d_cost:.3f}）"
    budget = cfg.beta0 + cfg.beta1 * d_score
    ok = d_cost <= budget
    return ok, f"cost_budget: ΔC={d_cost:.3f} vs 预算 {budget:.3f} (= {cfg.beta0} + {cfg.beta1}*{d_score:.3f})"


# ──────────────────────────────────────────────────────────────
# 闸 ④ 保留-扩展契约（#64）—— 本归档可信度最高的判据
# ──────────────────────────────────────────────────────────────
def preserve_extend(child_solved: set, parent_solved: set, cfg: GateConfig) -> tuple[bool, float, float, list[str]]:
    """g(c) > 0  且  R(c) <= delta

        g(c) = |S(c) \\ S(p)| - |S(p) \\ S(c)|     净增益（解出集）
        R(c) = |S(p) \\ S(c)|                     有界回退（交出了多少父代已解出的）

    #64 原话："必须在【至少一个任务上可测提升】，且不能交出超过小容差的、父代已解出的东西。"
    """
    gained = child_solved - parent_solved
    lost = parent_solved - child_solved
    g = len(gained) - len(lost)
    R = len(lost)
    reasons: list[str] = []
    if g <= 0:
        reasons.append(f"preserve_extend: 净增益 g={g} <= 0（gained={sorted(gained)}, lost={sorted(lost)}）")
    if R > cfg.regression_tolerance:
        reasons.append(f"preserve_extend: 回退 R={R} > 容差 {cfg.regression_tolerance}（lost={sorted(lost)}）")
    return (len(reasons) == 0), g, R, reasons


# ──────────────────────────────────────────────────────────────
# 汇总：双报 + 全闸
# ──────────────────────────────────────────────────────────────
LADDER = ("adopt", "in_domain_heldout", "ood", "cross_model")   # #64：按"分离度递增"排


@dataclass
class DualReport:
    """验收表必须【同时列 evolve(adopt) 集与 held-out 阶梯】；任一档回退 = 否决（铁律 19）。"""
    scores: dict = field(default_factory=dict)     # {档位: 分数}
    deltas: dict = field(default_factory=dict)     # {档位: 相对基座的变化}

    def regression_check(self, tol: float = 0.0) -> tuple[bool, list[str]]:
        bad = [t for t in LADDER[1:] if self.deltas.get(t, 0.0) < -tol]   # 从第 2 档起不许回退
        return (len(bad) == 0), [f"held-out 回退: {t} ({self.deltas[t]:+.4f})" for t in bad]


def evaluate(
    cand: Candidate,
    cfg: GateConfig | None = None,
    *,
    best_so_far: float | None = None,
    baseline_scores: list[float] | None = None,
    dual: DualReport | None = None,
    judge: "JudgeSpec | None" = None,
    pair: "PairBinding | None" = None,
) -> dict:
    """跑全部闸门并返回判决（fail-closed；任一闸不过 = admit=False）。"""
    cfg = cfg or GateConfig()
    reasons: list[str] = []
    info: dict[str, Any] = {}

    # 闸 ① 泄漏筛查（最早跑——泄漏候选不该拿到任何评估）
    ok_leak, r_leak = leak_screen(cand.diff, cfg)
    if not ok_leak:
        reasons.extend(r_leak)
    info["leak_screen"] = ok_leak

    # 闸 ④ 保留-扩展契约（#64）
    ok_pe, g, R, r_pe = preserve_extend(cand.child_solved, cand.parent_solved, cfg)
    if not ok_pe:
        reasons.extend(r_pe)
    info.update(g=g, R=R, preserve_extend=ok_pe)

    # 闸 ② 噪声地板（需要基座重复评测 + 候选的【绝对】分数）
    delta = None
    if baseline_scores:
        delta = noise_band(baseline_scores, cfg)
        if best_so_far is None:
            best_so_far = max(baseline_scores)
        if cand.score is None:
            reasons.append("noise_floor: 候选缺【绝对分数】score，无法过噪声地板（fail-closed）")
            info["noise_floor"] = False
        else:
            ok_nf, msg = passes_noise_floor(cand.score, best_so_far, delta)
            if not ok_nf:
                reasons.append(msg)
            info["noise_floor"] = ok_nf
        info["delta"] = delta
    else:
        reasons.append("noise_floor: 未提供基座重复评测 baseline_scores，噪声带无法估计（fail-closed）")
        info["noise_floor"] = False

    # 闸 ③ 成本预算（需要 delta）
    if delta is not None:
        ok_cb, msg = passes_cost_budget(cand.d_score, cand.d_cost, delta, cfg)
        if not ok_cb:
            reasons.append(msg)
        info["cost_budget"] = ok_cb

    # 闸 ⑤ 双速设计（#64）：未重测确认的候选不得驱动搜索
    if not cand.resolved:
        reasons.append("two-speed: 候选尚未通过【更高保真的重测/preservation probe】→ 不得驱动后续搜索（可不入档为负证据）")
    if not cand.verified:
        reasons.append("evidence: 证据未来自可信 verifier（fail-closed）")
    info["two_speed"] = cand.resolved and cand.verified

    # 闸 ⑥ 双报 + OOD 优先（铁律 19）
    if dual is not None:
        ok_dual, r_dual = dual.regression_check()
        if not ok_dual:
            reasons.extend(r_dual)
        info["dual_report"] = ok_dual

    # 闸 ⑨ 评判器可靠性（清单第③条①）—— 有则判；无则由 strict_admission 决定
    if judge is not None:
        ok_j, r_j, i_j = judge_reliability(judge, cfg)
        if not ok_j:
            reasons.extend(r_j)
        info["judge_reliability"] = ok_j
        info.update({k: v for k, v in i_j.items() if k not in ("passed",)})
    elif cfg.strict_admission:
        reasons.append("judge_reliability: 严格准入模式要求提供评判器可靠性（清单第③条①）"
                       "，未提供 ⇒ 拒（fail-closed）")
        info["judge_reliability"] = False

    # 闸 ⑩ 上下游成对兼容（清单第③条②）
    if pair is not None:
        ok_p, r_p, i_p = pairwise_compat(pair, cfg)
        if not ok_p:
            reasons.extend(r_p)
        info["pairwise_compat"] = ok_p
        info.update(i_p)
    elif cfg.strict_admission:
        reasons.append("pairwise_compat: 严格准入模式要求提供上下游成对兼容声明（清单第③条②）"
                       "，未提供 ⇒ 拒（fail-closed）")
        info["pairwise_compat"] = False

    return {
        "candidate": cand.name,
        "admit": len(reasons) == 0,
        "reasons": reasons,
        "net_gain_g": g,
        "bounded_regression_R": R,
        "noise_delta": delta,
        **info,
    }


# ──────────────────────────────────────────────────────────────
# 闸 ⑦ 双阈值 + 空状态兜底（#65 RSEA 2026-06-17）—— 全归档最精确的判据形式
# ──────────────────────────────────────────────────────────────
@dataclass
class ValStep:
    """一代的候选在【held-out val】上的得分。不相交的 evolve/val 是前提。"""
    name: str
    val_score: float


def rsea_select(steps: list, base_val: float | None = None) -> dict:
    """#65 的严格 held-out keep-better 选择。

        accept : v >= 现任 val 分      ← 【横移】(>=)，让搜索逃离平台
        promote: v >  frozen_best 分    ← 【严格】(>)，只有它更新冻结最优
        fail   : 若无候选严格改进      → 返回【空状态】= 系统原始行为

    ⭐ #65 原话："这个不对称性就是关键：横移接受让搜索逃离平台，而严格最优更新保证
       返回的状态在 held-out val 上永不差于基线——若无严格改进就退回空状态。"
    ⚠️ 注意 accept 与 promote 是【两个不同阈值】：非严格的 >= 晋升会让"只在小的/
       不具代表性的 val 抽样上打平"的候选被冻结，然后在 test 上造成伤害。
    """
    working: ValStep | None = None      # 当前工作状态（可横移）
    frozen: ValStep | None = None       # 冻结最优（只严格晋升）；None = 空状态
    best_score = base_val
    lateral, promoted = [], []
    attempts: list = []

    for st in steps:
        attempts.append(st)
        cur_val = working.val_score if working is not None else (base_val or 0.0)
        # ① 横移接受：不回退即可（≥）
        if st.val_score >= cur_val:
            working = st
            lateral.append(st.name)
        # ② 严格晋升：只有真正更好才更新冻结最优（>）
        if best_score is None or st.val_score > best_score:
            frozen, best_score = st, st.val_score
            promoted.append(st.name)

    # ⭐ #71 RSIBench-Data：必须【分开报】"历史最优"与"最后尝试"
    #    实测：首次达峰后继续搜索的 23 个设置里，18 个(78.26%)最终尝试【低于】峰值、5 个打平、0 个超过。
    last = attempts[-1] if attempts else None
    last_vs_peak = None
    if last is not None and frozen is not None:
        last_vs_peak = round(last.val_score - frozen.val_score, 4)

    return {
        "frozen_best": frozen.name if frozen else "__EMPTY__(= 系统原始行为)",
        "frozen_best_score": best_score,
        "lateral_accepts": lateral,          # 允许横移（逃平台）
        "strict_promotions": promoted,       # 只有这些驱动最终交付
        "fallback_to_empty": frozen is None, # ⭐ 空状态兜底
        "last_attempt": last.name if last else None,              # ⭐ #71 要求同时报
        "last_attempt_score": last.val_score if last else None,   # ⭐
        "last_vs_peak": last_vs_peak,   # <0 = 继续搜索后【低于】峰值（#71: 78.26% 如此）
        # ⭐ 单调安全 = 返回的状态【永不差于】基线：
        #    - 有冻结最优 → 严格晋升(>)保证它优于基线
        #    - 无冻结最优 → 返回空状态 = 基线本身，同样安全（这正是兜底的意义）
        "monotone_safe_vs_base": (
            (frozen is None) or (base_val is None) or (best_score > base_val)
        ),
    }


# ──────────────────────────────────────────────────────────────
# 闸 ⑧ 新颖度门（#66 aTTT 2026-07-03）—— 分级降权，而非二元丢弃
# ──────────────────────────────────────────────────────────────
def repetition_ratio(text: str, history: list, n: int = 1) -> float:
    """#66 的 ρ：与本 episode 内任一先前文本的【最大词级 Jaccard 重叠】。

    注意 #66 原文用 n=1（词集）；高 ρ = "卡住"的操作信号。
    """
    def ngrams(s, k):
        w = s.split()
        return set(tuple(w[i:i + k]) for i in range(len(w) - k + 1)) if k > 1 else set(w)
    cur = ngrams(text, n)
    if not cur or not history:
        return 0.0
    best = 0.0
    for h in history:
        prev = ngrams(h, n)
        if not prev:
            continue
        j = len(cur & prev) / len(cur | prev)
        best = max(best, j)
    return best


def novelty_weights(text: str, history: list, n: int = 3, w_min: float = 0.1) -> list:
    """#66 的 token 级权重：w_j = max(w_min, 1 / (1 + f_j))。

    f_j = 位置 j 所属 n-gram 在【先前更新历史】中的最大曝光次数。
    没出现在重复 n-gram 里的 token 权重 = 1（新颖 token 保持全权重）。
    """
    toks = text.split()
    L = len(toks)
    if L == 0:
        return []
    # 统计历史里的 n-gram 频次
    from collections import Counter
    hist_counts = Counter()
    for h in history:
        w = h.split()
        for i in range(max(0, len(w) - n + 1)):
            hist_counts[tuple(w[i:i + n])] += 1
    weights = []
    for j in range(L):
        best_f = 0
        for i in range(max(0, j - n + 1), min(j, L - n) + 1):
            if L - n < 0:
                break
            g = tuple(toks[i:i + n])
            best_f = max(best_f, hist_counts.get(g, 0))
        weights.append(max(w_min, 1.0 / (1.0 + best_f)))
    return weights


def novelty_summary(text: str, history: list, n: int = 3, w_min: float = 0.1) -> dict:
    """给一条候选文本的新颖度报告：重复度 ρ + 权重向量 + 有效新颖比。"""
    w = novelty_weights(text, history, n=n, w_min=w_min)
    full = sum(1 for x in w if x >= 0.999)
    return {
        "repetition_rho": round(repetition_ratio(text, history, n=1), 4),
        "n_tokens": len(w),
        "novel_tokens_fully_weighted": full,
        "mean_weight": round(sum(w) / len(w), 4) if w else 0.0,
        "should_downgrade": (sum(w) / len(w) if w else 1.0) < 0.5,   # #66: 新颖度 <0.5 → 更新收益小
    }


# ──────────────────────────────────────────────────────────────
# 闸 ⑨ 评判器可靠性（设计清单 v1 第③条 ①）
#   问题：闸只查「变更是否合规」，却不查【量尺本身】——
#         评判器可靠吗？校准过吗？什么时候更新的？判别力还在吗？
#   依据：铁律 15（判别力 r_disc→0 = 判据已死）/ 铁律 46（先报锚点自身噪声）
#         / 铁律 10（独立验证者按底层模型身份计数）
# ──────────────────────────────────────────────────────────────
@dataclass
class JudgeSpec:
    """评判器（验证器）自身的可靠性状态。任一关键项缺失 ⇒ fail-closed。"""
    judge_id: str = ""
    agreement: float | None = None          # 与锚点/人类的一致度（如 Cohen's κ）
    anchor_agreement: float | None = None   # ⭐ 锚点【自身】的一致度（人-人 / 锚-锚）= 噪声地板（铁律 46）
    n_anchor: int = 0                       # 校准样本量
    updated_utc: str = ""                   # 上次更新时间（ISO 日期，如 '2026-10-01'）
    discriminative_power: float | None = None   # r_disc = std(判据在候选集上的打分)
    independence: int = 0                   # 独立验证者数量（按底层模型身份计）


def judge_reliability(judge: "JudgeSpec | None", cfg: "GateConfig",
                      today: str | None = None) -> tuple[bool, list[str], dict]:
    """判「量尺还能不能用」。返回 (passed, reasons, info)；fail-closed。"""
    import datetime as _dt
    reasons: list[str] = []
    info: dict = {"judge_id": getattr(judge, "judge_id", "")}
    if judge is None:
        return False, ["judge_reliability: 未提供评判器可靠性（清单第③条①）⇒ fail-closed"], info

    # ① 一致度必须存在
    if judge.agreement is None:
        reasons.append("judge_reliability: 缺 agreement（与锚点/人类的一致度）⇒ 未校准的评判器不得准入")
    # ② 校准样本量
    if judge.n_anchor < cfg.judge_min_anchor_n:
        reasons.append(f"judge_reliability: 校准样本量 n={judge.n_anchor} < 下限 {cfg.judge_min_anchor_n}")
    # ③ ⭐ 铁律 46：必须先有【锚点自身】的噪声地板，且评判器要【超过】它
    if judge.anchor_agreement is None:
        reasons.append("judge_reliability: 缺 anchor_agreement（锚点自身一致度）⇒ 只报了"
                       "『与专家一致 X%』却没说『专家与专家一致多少』（铁律 46）")
    elif judge.agreement is not None:
        margin = judge.agreement - judge.anchor_agreement
        info["margin_over_anchor"] = round(margin, 4)
        if margin < cfg.judge_margin:
            reasons.append(f"judge_reliability: 评判器一致度 {judge.agreement:.3f} 仅高出锚点自身"
                           f" {judge.anchor_agreement:.3f} 的差 {margin:+.3f} < 要求 {cfg.judge_margin}"
                           f" ⇒ 该评判器【没带来信息】（不比锚点自身更一致）")
    # ④ 铁律 15：判别力可测且未死
    if judge.discriminative_power is None:
        reasons.append("judge_reliability: 缺 discriminative_power（r_disc）⇒ 判据是否已死无从判断（铁律 15）")
    elif judge.discriminative_power <= cfg.judge_min_r_disc:
        reasons.append(f"judge_reliability: r_disc={judge.discriminative_power:.6f} <= {cfg.judge_min_r_disc}"
                       f" ⇒ 该判据【已死】（对所有候选打同一个分）")
    # ⑤ 上次更新时间（清单第③条①的「上次更新时间」栏）
    if not judge.updated_utc:
        reasons.append("judge_reliability: 缺 updated_utc（上次更新时间）")
    else:
        try:
            upd = _dt.date.fromisoformat(judge.updated_utc[:10])
            ref = _dt.date.fromisoformat(today[:10]) if today else _dt.date.today()
            age = (ref - upd).days
            info["age_days"] = age
            if age > cfg.judge_max_age_days:
                reasons.append(f"judge_reliability: 校准已过期 {age} 天 > {cfg.judge_max_age_days} 天 ⇒ 过期锚点不得准入")
        except ValueError:
            reasons.append(f"judge_reliability: updated_utc 不是 ISO 日期：{judge.updated_utc!r}")
    # ⑥ 独立性（按底层模型身份计数）
    if judge.independence < cfg.judge_min_independence:
        reasons.append(f"judge_reliability: 独立验证者 {judge.independence} < 下限 {cfg.judge_min_independence}"
                       f"（按底层模型身份计，铁律 10）")
    info["passed"] = len(reasons) == 0
    return info["passed"], reasons, info


# ──────────────────────────────────────────────────────────────
# 闸 ⑩ 上下游成对兼容（设计清单 v1 第③条 ②）
#   问题：只查【零件】（「预测器更准了」）不查【装配】
#         ⇒ 策略一换，原本更好的预测器反而不可靠。
#   四要件：① 上游绑定（sha）② 下游声明齐 ③ 下游逐个复验 ④ 装配后行为重测
# ──────────────────────────────────────────────────────────────
@dataclass
class PairBinding:
    """变更的上下游绑定声明。四要件缺一即拒。"""
    upstream_sha: str = ""                    # 变更所基于的上游版本 sha
    current_sha: str = ""                     # 准入时刻读到的【实际】sha
    downstream_consumers: list = field(default_factory=list)   # 声明的消费方
    downstream_tested: list = field(default_factory=list)      # 已【成对复验】的消费方
    pair_behavior_test: bool = False          # ⭐ 是否重测了【装配后系统的决策行为】（而非只测组件指标）
    note: str = ""


def pairwise_compat(pair: "PairBinding | None", cfg: "GateConfig") -> tuple[bool, list[str], dict]:
    """判「这份变更和它的上下游还配不配」。返回 (passed, reasons, info)；fail-closed。"""
    reasons: list[str] = []
    info: dict = {}
    if pair is None:
        return False, ["pairwise_compat: 未提供上下游绑定声明（清单第③条②）⇒ fail-closed"], info

    # ① 上游绑定：变更必须基于【当前】上游，否则是陈旧基线（丢更新）
    if not pair.upstream_sha or not pair.current_sha:
        reasons.append("pairwise_compat: 缺 upstream_sha/current_sha ⇒ 无法确认变更基于哪一版上游")
        info["upstream_bound"] = False
    else:
        info["upstream_bound"] = (pair.upstream_sha == pair.current_sha)
        if not info["upstream_bound"]:
            reasons.append(f"pairwise_compat: 上游不绑定（变更基于 {pair.upstream_sha[:12]}，"
                           f"当前为 {pair.current_sha[:12]}）⇒ 陈旧基线，须 rebase 后重测")
    # ② 下游必须被声明
    if not pair.downstream_consumers:
        reasons.append("pairwise_compat: 未声明 downstream_consumers ⇒ 无从判断装配影响（只查零件）")
    # ③ 成对复验：声明的下游必须【逐个】被复验
    missing = sorted(set(pair.downstream_consumers) - set(pair.downstream_tested))
    info["downstream_missing"] = missing
    if missing:
        reasons.append(f"pairwise_compat: 下游未【成对】复验：{missing} ⇒ 策略换后这些消费方是否仍可靠未知")
    # ④ ⭐ 装配后行为：必须测「装配后系统的决策行为」，不是只测组件
    if not pair.pair_behavior_test:
        reasons.append("pairwise_compat: 只测了组件，未重测【装配后系统的决策行为】"
                       "（反面例：策略换后，原本更好的预测器反而不可靠）")
    info["passed"] = len(reasons) == 0
    return info["passed"], reasons, info


# ──────────────────────────────────────────────────────────────
# 自检 demo —— 复现 #63/#64/#65/#66 的关键对比
# ──────────────────────────────────────────────────────────────
def _demo() -> int:
    print("=" * 74)
    print("rsi_gate.py 自检  ——  依据 #63 RRSI / #64 DarwinX")
    print("=" * 74)

    cfg = GateConfig()
    base_reps = [61.0, 62.5, 60.8, 61.7, 62.0]        # 基座重复评测（估噪声带）
    delta = noise_band(base_reps, cfg)
    print(f"\n[0] 基座重复评测 {base_reps} → 噪声带 delta = {delta:.4f}")

    tasks = [f"t{i}" for i in range(41)]
    parent = set(tasks[:20])

    print("\n" + "-" * 74)
    print("[A] 干净的改进（扩 3 题、不退）—— 应【放行】")
    childA = set(tasks[:23])
    candA = Candidate("improver", diff="+ 新增 verify-and-retry 控制流", parent_solved=parent,
                      child_solved=childA, score=65.5, resolved=True, verified=True,
                      d_score=3.0, d_cost=0.15)
    dualA = DualReport(deltas={"adopt": 3.0, "in_domain_heldout": 1.2, "ood": 0.8, "cross_model": 0.3})
    rA = evaluate(candA, cfg, best_so_far=62.5, baseline_scores=base_reps, dual=dualA)
    print("   ", "✅ ADMIT" if rA["admit"] else "❌ REJECT", f"g={rA['net_gain_g']} R={rA['bounded_regression_R']}")
    for x in rA["reasons"]:
        print("      -", x)

    print("\n" + "-" * 74)
    print("[B] 泄漏候选（把基准名写进 prompt）—— 应【在评估前就被拒】")
    candB = Candidate("leaker", diff="+ if task_id.startswith('Terminal-Bench 2.1'): return known_answer",
                      parent_solved=parent, child_solved=set(tasks[:25]), score=67.5,
                      resolved=True, verified=True, d_score=5.0, d_cost=0.05)
    rB = evaluate(candB, cfg, best_so_far=62.5, baseline_scores=base_reps)
    print("   ", "✅ ADMIT" if rB["admit"] else "❌ REJECT")
    for x in rB["reasons"]:
        print("      -", x)

    print("\n" + "-" * 74)
    print("[C] 用 3 个已解换 5 个新解（R=3 > 容差 0.5）—— 应【拒】（不许回退）")
    childC = (parent - set(tasks[17:20])) | set(tasks[20:25])
    candC = Candidate("trader", diff="+ 换掉既有机制", parent_solved=parent, child_solved=childC,
                      score=64.5, resolved=True, verified=True, d_score=2.0, d_cost=0.20)
    rC = evaluate(candC, cfg, best_so_far=62.5, baseline_scores=base_reps)
    print("   ", "✅ ADMIT" if rC["admit"] else "❌ REJECT", f"g={rC['net_gain_g']} R={rC['bounded_regression_R']}")
    for x in rC["reasons"]:
        print("      -", x)

    print("\n" + "-" * 74)
    print("[D] 只在 adopt 集上好看（adopt +4.0，但 OOD −0.3 / 跨模型 −0.6）—— 应【拒】（铁律 19）")
    candD = Candidate("bench_overfit", diff="+ 大量基准特定补丁", parent_solved=parent,
                      child_solved=set(tasks[:23]), score=64.0, resolved=True, verified=True,
                      d_score=1.5, d_cost=0.57)
    dualD = DualReport(deltas={"adopt": 4.0, "in_domain_heldout": 0.2, "ood": -0.3, "cross_model": -0.6})
    rD = evaluate(candD, cfg, best_so_far=62.5, baseline_scores=base_reps, dual=dualD)
    print("   ", "✅ ADMIT" if rD["admit"] else "❌ REJECT")
    for x in rD["reasons"]:
        print("      -", x)

    print("\n" + "-" * 74)
    print("[E] 双速：尚未重测确认 —— 可入档为负证据，但【不得驱动搜索】")
    candE = Candidate("unverified", diff="+ 一个可疑改动", parent_solved=parent,
                      child_solved=set(tasks[:24]), score=64.5, resolved=False, verified=True,
                      d_score=2.0, d_cost=0.10)
    rE = evaluate(candE, cfg, best_so_far=62.5, baseline_scores=base_reps)
    print("   ", "✅ ADMIT" if rE["admit"] else "❌ REJECT")
    for x in rE["reasons"]:
        print("      -", x)

    print("\n" + "=" * 74)
    print("结论：A 放行；B(泄漏)/C(回退)/D(OOD 回退)/E(未重测) 全部拒绝。")
    print("      ⭐ 高 evolve 分（D: adopt +4.0）【买不掉】OOD 回退 —— 铁律 19 的机器形态。")
    print("=" * 74)

    # ── #65 RSEA 双阈值 + 空状态兜底 ──────────────────────────
    print("\n" + "=" * 74)
    print("[#65] RSEA 双阈值选择（accept ≥ 横移 / promote > 严格 / 无改进→空状态）")
    print("=" * 74)

    print("\n[F] 横移逃平台：0.62 →(横移) 0.62 →(横移) 0.63 → 0.71")
    seqF = [ValStep("g1_drop_redundancy", 0.62),   # 打平：横移，不改冻结最优
            ValStep("g2_rewrite_strategy", 0.62),  # 打平：横移，不改冻结最优
            ValStep("g3_add_skill", 0.63),          # 微升：横移 + 严格晋升
            ValStep("g4_add_playbook", 0.71)]       # 再升：横移 + 严格晋升
    rF = rsea_select(seqF, base_val=0.62)
    print("    冻结最优 =", rF["frozen_best"], f"({rF['frozen_best_score']})")
    print("    横移接受 =", rF["lateral_accepts"])
    print("    严格晋升 =", rF["strict_promotions"])
    print("    ⭐ 前面两次打平【没有】污染冻结最优 —— 这就是 accept 与 promote 必须分开")

    print("\n[G] 无任何严格改进 → 兜底回空状态（= 系统原始行为），构造性单调安全")
    seqG = [ValStep("g1_worse", 0.55), ValStep("g2_also_worse", 0.58)]
    rG = rsea_select(seqG, base_val=0.62)
    print("    冻结最优 =", rG["frozen_best"])
    print("    fallback_to_empty =", rG["fallback_to_empty"],
          "｜ monotone_safe_vs_base =", rG["monotone_safe_vs_base"])

    print("\n[对照] 同一个 [F] 序列，若只用【单阈值 ≥】晋升（#65 警告的做法）")
    single = ValStep("g2_rewrite_strategy", 0.62)     # 打平项
    print(f"    ⚠️ 非严格 ≥ 会把打平项 {single.name}(val={single.val_score}) 当成改进而冻结")
    print("       → #65 实测：这类候选在小/不具代表性 val 上打平，然后在 test 上造成伤害")
    print("       （无门的 Dynamic Cheatsheet：ALFWorld 70.7% 近最佳 → WebShop 0.14 vs ReAct 0.43）")

    print("\n" + "=" * 74)
    print("[#66] 新颖度门（分级降权，而非二元丢弃）")
    print("=" * 74)

    hist = ["open fridge take apple from fridge then go to counter",
            "open fridge take apple from fridge then go to counter again"]
    print("\n[H] 一条【高度重复】的更新（大面积复述历史）")
    rep = "open fridge take apple from fridge then go to counter then open fridge take apple"
    s_rep = novelty_summary(rep, hist)
    print("     ", s_rep)

    print("\n[I] 一条【部分重复 + 含新信息】的更新（#66 说这才是不该整条丢的情况）")
    mix = "open fridge take apple from fridge then find the knife on the counter and use it"
    s_mix = novelty_summary(mix, hist)
    print("     ", s_mix)
    w = novelty_weights(mix, hist)
    print("      逐词权重:", [f"{t}:{x:.2f}" for t, x in zip(mix.split(), w)])

    print("\n[J] 一条【全新】的更新")
    fresh = "microwave the potato for three minutes then place it in the sink"
    s_fresh = novelty_summary(fresh, hist)
    print("     ", s_fresh)

    print("\n[对照] 二元丢弃 vs 分级降权（#66 的核心论据）")
    print("     二元丢弃 H:   整条不要  → 连里面可能的新 token 一起丢")
    print(f"     分级降权 I:   保留全部 token，但重复片段降权 →",
          f"新颖 token 仍全权重({s_mix['novel_tokens_fully_weighted']}/{s_mix['n_tokens']})")
    print(f"     分级降权 J:   几乎无重复 → mean_weight={s_fresh['mean_weight']}（等效不降权）")

    print("\n[K] ⭐ #71 的形态：首次达峰后【继续搜索最终变差】—— 必须分开报")
    seqK = [ValStep("g1", 0.62), ValStep("g2_peak", 0.71),
            ValStep("g3_below", 0.68), ValStep("g4_lower", 0.65)]
    rK = rsea_select(seqK, base_val=0.62)
    print(f"    frozen_best      = {rK['frozen_best']} ({rK['frozen_best_score']})")
    print(f"    last_attempt     = {rK['last_attempt']} ({rK['last_attempt_score']})")
    print(f"    last_vs_peak     = {rK['last_vs_peak']}   ← <0 = 继续搜索后低于峰值")
    print("    ⭐ 若只报 last_attempt 你会以为退化；报 frozen_best 才是诚实交付")
    print("       （#71 实测：78.26% 的继续搜索都落在这种形态）")

    # ══════════════════════════════════════════════════════════════
    # MR5 · 校准（negative control）
    #   已知好 / 已知坏 输入 ⇒ 【事先写死】的预期判定，逐条核对。
    #   这不是演示：任一条偏离预期 ⇒ cal_ok=False ⇒ 自检 exit != 0。
    # ══════════════════════════════════════════════════════════════
    print("\n" + "=" * 74)
    print("MR5 · 校准（negative control）：已知输入 ⇒ 事先写死的预期判定")
    print("=" * 74)
    calibration = [
        ("A_clean_gain",  rA, True,  "干净的改进（扩 3 题、不退） ⇒ 应放行"),
        ("B_leak",        rB, False, "基准名写进 diff ⇒ 泄漏，应在评估前拒"),
        ("C_regression",  rC, False, "回退 R=3 > 容差 0.5 ⇒ 应拒"),
        ("D_ood_regress", rD, False, "adopt +4 但 OOD −0.3 ⇒ 铁律 19 不许买断"),
        ("E_unverified",  rE, False, "未重测 ⇒ 证据不足，fail-closed 应拒"),
    ]
    for nm, v, exp, why in calibration:
        got = "ADMIT" if v["admit"] else "REJECT"
        want = "ADMIT" if exp else "REJECT"
        print(f'  {"✅" if v["admit"] is exp else "❌"} {nm:<14} 实判={got:<6} 预期={want:<6} {why}')
    cal_ok = all(v["admit"] is exp for _, v, exp, _ in calibration)
    print(f'  校准判决: {"✅ 5/5 命中预期" if cal_ok else "❌ 有用例偏离预期 ⇒ 闸已坏"}')

    # ⭐ 校准的【阴性对照】: 故意把闸弄坏，校准必须报错。
    #    若坏闸下校准仍"通过"，那这块只是装饰 —— 它抓不到坏闸（= MR5 想防的事）。
    for probe_name, broken_cfg, probe_cand, expect_broken_admit in (
            ("容差 0.5 → 999", GateConfig(regression_tolerance=999.0), candC, True),):
        rb = evaluate(probe_cand, broken_cfg, best_so_far=62.5, baseline_scores=base_reps)
        caught = (rb["admit"] is not False)
        print(f'  校准自检: 把 {probe_name} 后, [C] 实判={("ADMIT" if rb["admit"] else "REJECT")} '
              f'⇒ 校准{"能抓住坏闸 ✅" if caught else "抓不住坏闸 ❌（校准无效）"}')
    cal_catches_broken = caught

    # ══════════════════════════════════════════════════════════════
    # MR2 · 判别力分布（输出不能只剩一个取值）
    # ══════════════════════════════════════════════════════════════
    admits = [v["admit"] for _, v, _, _ in calibration]
    judged_scores = [c.score for c in (candA, candB, candC, candD, candE) if c.score is not None]
    distribution = dict(
        n_judged=len(admits), n_admit=sum(admits), n_reject=len(admits) - sum(admits),
        admit_ratio=round(sum(admits) / len(admits), 3),
        judged_score_std=round(statistics.stdev(judged_scores), 4) if len(judged_scores) > 1 else 0.0,
        baseline_noise_std=round(statistics.stdev(base_reps), 4),
    )
    print("\n" + "=" * 74)
    print("MR2 · 判别力分布（非单值：至少一放行、一拒绝，且分数有散布）")
    print("=" * 74)
    print("  " + "  ".join(f"{k}={v}" for k, v in distribution.items()))
    dist_ok = (distribution["n_admit"] >= 1 and distribution["n_reject"] >= 1
               and distribution["judged_score_std"] > 0)
    print(f'  分布判决: {"✅ 判定非退化" if dist_ok else "❌ 判定退化或分数无散布"}')

    # ══════════════════════════════════════════════════════════════
    # MR6 · 翻转条件（reopen_if）
    # ══════════════════════════════════════════════════════════════
    print("\n" + "=" * 74)
    print("MR6 · 翻转条件 reopen_if —— 每条阈值在什么情况下该被推翻重来")
    print("=" * 74)
    for key, item in reopen_if.items():
        print(f'  · {key}')
        print(f'      阈值 {item["threshold"]}')
        print(f'      翻转 {item["flip"]}')
        print(f'      复测 {item["remeasure"]}')

    # ══════════════════════════════════════════════════════════════
    # 闸 ⑨ / 闸 ⑩ · 设计清单 v1 第③条（评判器可靠性 / 上下游成对兼容）
    #   "缺这两栏的闸，等于只查零件不查装配"
    # ══════════════════════════════════════════════════════════════
    from dataclasses import replace

    print("\n" + "=" * 74)
    print("闸 ⑨ 评判器可靠性（清单第③条①）—— 只查变更合规、不查量尺，是不完整的")
    print("=" * 74)
    TODAY = "2026-10-13"
    good_judge = JudgeSpec(judge_id="llm-judge-v3", agreement=0.80, anchor_agreement=0.62,
                           n_anchor=202, updated_utc="2026-09-30",
                           discriminative_power=0.21, independence=2)
    judges = [
        ("good",            good_judge,                                            True),
        ("dead(r_disc=0)",  replace(good_judge, discriminative_power=0.0),         False),
        ("stale(>180d)",    replace(good_judge, updated_utc="2026-01-05"),         False),
        ("weak(<=anchor)",  replace(good_judge, agreement=0.64),                   False),
        ("no_anchor_floor", replace(good_judge, anchor_agreement=None),            False),
        ("tiny_n",          replace(good_judge, n_anchor=5),                       False),
        ("no_timestamp",    replace(good_judge, updated_utc=""),                   False),
    ]
    judge_ok = True
    for nm, j, exp in judges:
        ok_j, r_j, _ = judge_reliability(j, cfg, today=TODAY)
        if ok_j is not exp:
            judge_ok = False
        tag = "✅" if ok_j is exp else "❌"
        tail = "" if exp else "  ← " + (r_j[0][:104] if r_j else "")
        print(f'  {tag} {nm:<16} 实判={"PASS" if ok_j else "REJECT":<6} 预期={"PASS" if exp else "REJECT":<6}{tail}')

    print("\n" + "=" * 74)
    print("闸 ⑩ 上下游成对兼容（清单第③条②）—— 只查零件不查装配")
    print("=" * 74)
    good_pair = PairBinding(upstream_sha="a" * 12, current_sha="a" * 12,
                            downstream_consumers=["rsi_gate", "self-reinforcement", "cortexmem"],
                            downstream_tested=["rsi_gate", "self-reinforcement", "cortexmem"],
                            pair_behavior_test=True)
    pairs = [
        ("bound+all_tested", good_pair, True),
        ("stale_upstream",   replace(good_pair, current_sha="b" * 12),                       False),
        ("no_downstream",    replace(good_pair, downstream_consumers=[], downstream_tested=[]), False),
        ("partial_tested",   replace(good_pair, downstream_tested=["rsi_gate"]),             False),
        ("component_only",   replace(good_pair, pair_behavior_test=False),                   False),
    ]
    pair_ok = True
    for nm, p, exp in pairs:
        ok_p, r_p, _ = pairwise_compat(p, cfg)
        if ok_p is not exp:
            pair_ok = False
        tag = "✅" if ok_p is exp else "❌"
        tail = "" if exp else "  ← " + (r_p[0][:104] if r_p else "")
        print(f'  {tag} {nm:<16} 实判={"PASS" if ok_p else "REJECT":<6} 预期={"PASS" if exp else "REJECT":<6}{tail}')

    print("\n[兼容/严格] 同一条【旧格式】候选（无 judge / 无 pair）—— 新栏是否破坏旧契约")
    r_compat = evaluate(candA, cfg, best_so_far=62.5, baseline_scores=base_reps, dual=dualA)
    r_strict = evaluate(candA, GateConfig(strict_admission=True), best_so_far=62.5,
                        baseline_scores=base_reps, dual=dualA)
    print(f'   兼容模式(默认 strict_admission=False): {"ADMIT" if r_compat["admit"] else "REJECT"}'
          f'   ← 旧调用方零影响')
    print(f'   严格模式(strict_admission=True)      : {"ADMIT" if r_strict["admit"] else "REJECT"}'
          f'   ← 缺两栏即拒（新栏成为硬闸）')
    compat_ok = (r_compat["admit"] is True) and (r_strict["admit"] is False)
    if not compat_ok:
        print("   ❌ 兼容/严格两模式未区分开 ⇒ 开关可能没接上")

    print("\n" + "=" * 74)
    print("新闸阴性对照：把判据弄坏，必须能被抓住（否则只是装饰）")
    print("=" * 74)
    nc_ok = True
    relaxed = judge_reliability(replace(good_judge, discriminative_power=0.0),
                                GateConfig(judge_min_r_disc=-1.0), today=TODAY)
    hit1 = (relaxed[0] is True)
    nc_ok &= hit1
    print(f'  [⑨] 把 judge_min_r_disc 放宽到 −1 ⇒ 死判据 实判={"PASS" if relaxed[0] else "REJECT"}'
          f' ⇒ {"该条判据确实在起作用 ✅" if hit1 else "该条形同虚设 ❌"}')
    hit2 = (pairwise_compat(replace(good_pair, current_sha="b" * 12), cfg)[0] is False)
    nc_ok &= hit2
    print(f'  [⑩] 上游 sha 不匹配 ⇒ {"能抓住陈旧基线 ✅" if hit2 else "抓不住 ❌"}')
    hit3 = (judge_reliability(replace(good_judge, anchor_agreement=None), cfg, today=TODAY)[0] is False)
    nc_ok &= hit3
    print(f'  [⑨] 只报「与专家一致 X%」不给锚点噪声 ⇒ {"能抓住（铁律 46）✅" if hit3 else "抓不住 ❌"}')

    print("\n" + "=" * 74)
    ok = (rA["admit"] and not any(r["admit"] for r in (rB, rC, rD, rE))
          and rF["frozen_best"] == "g4_add_playbook"
          and rG["fallback_to_empty"] and rG["monotone_safe_vs_base"]
          and s_rep["mean_weight"] < s_mix["mean_weight"] < s_fresh["mean_weight"]
          and s_fresh["mean_weight"] >= 0.999
          and rK["frozen_best"] == "g2_peak" and rK["last_vs_peak"] is not None and rK["last_vs_peak"] < 0
          and cal_ok and cal_catches_broken and dist_ok
          and judge_ok and pair_ok and compat_ok and nc_ok)
    print("总检:", "✅ 全部符合预期" if ok else "❌ 有断言不符")
    print("       ⭐ #66: mean_weight 应满足 重复 < 部分重复 < 全新(=1)")
    print("       ⭐ #71: frozen_best 应保在峰值, 且 last_vs_peak < 0（搜索退化可见）")
    print("       ⭐ MR5 校准（含「校准自检」） · MR2 分布 · MR6 reopen_if —— 三者均真值，非装饰")
    print("       ⭐ 闸⑨评判器可靠性 / 闸⑩上下游成对兼容（设计清单 v1 第③条）—— 含阴性对照与兼容性证明")
    print("=" * 74)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_demo())
