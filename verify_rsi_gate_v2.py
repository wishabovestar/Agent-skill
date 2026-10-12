#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_rsi_gate_v2.py —— rsi_gate 新增两栏的【独立】验证（不复用 _demo 的 fixtures）。

独立性的含义：本脚本自己造 fixture、自己写死预期、逐条断言，
并检查【失败原因的具体文本】是否命中预期子串（防「只是碰巧拒了」）。

用法： python verify_rsi_gate_v2.py     # exit 0 = 全部命中
"""
import sys, pathlib, importlib.util

HERE = pathlib.Path(__file__).resolve()
RSI = pathlib.Path(r"D:/hermes/analysis/rsi_gate.py")
spec = importlib.util.spec_from_file_location("rsi_gate_mod", RSI)
m = importlib.util.module_from_spec(spec)
sys.modules["rsi_gate_mod"] = m          # ⭐ 必须登记：dataclasses 要靠 __module__ 反查命名空间
spec.loader.exec_module(m)

from dataclasses import replace
FAILS = []
def ck(cond, label, extra=""):
    print(f'  {"✅" if cond else "❌"} {label}{("  " + extra) if extra else ""}')
    if not cond: FAILS.append(label)

print("=" * 74)
print("独立验证 · 闸⑨ 评判器可靠性（自己造的 fixture，逐条给预期子串）")
print("=" * 74)
J = m.JudgeSpec
cfg = m.GateConfig()
T = "2026-10-13"
BASE = dict(judge_id="probe-judge", agreement=0.78, anchor_agreement=0.60, n_anchor=150,
            updated_utc="2026-10-01", discriminative_power=0.15, independence=2)
cases = [
    ("未提供 judge",                 None,                                            "未提供评判器可靠性"),
    ("r_disc = 0（判据已死）",        dict(discriminative_power=0.0),                  "已死"),
    ("r_disc 缺失",                  dict(discriminative_power=None),                 "r_disc"),
    ("agreement 低于锚点噪声",        dict(agreement=0.61),                            "没带来信息"),
    ("agreement 恰等于锚点",          dict(agreement=0.60),                            "没带来信息"),
    ("缺 anchor_agreement",          dict(anchor_agreement=None),                     "锚点自身"),
    ("n_anchor = 19（差 1）",         dict(n_anchor=19),                               "校准样本量"),
    ("updated 恰超期 1 天",           dict(updated_utc="2026-04-15"),                  "过期"),   # 2026-04-15→10-13 = 181 天
    ("updated 格式非法",              dict(updated_utc="2026/10/01"),                  "ISO"),
    ("independence = 0",             dict(independence=0),                           "独立验证者"),
]
ok_good, r_good, i_good = m.judge_reliability(J(**BASE), cfg, today=T)
ck(ok_good is True, "已知【好】评判器 ⇒ PASS", f"(margin={i_good.get('margin_over_anchor')}, age={i_good.get('age_days')}d)")
for nm, patch, need in cases:
    j = None if patch is None else J(**{**BASE, **patch})
    ok, rs, _ = m.judge_reliability(j, cfg, today=T)
    hit = (ok is False) and any(need in r for r in rs)
    ck(hit, f"{nm} ⇒ REJECT 且原因含「{need}」", "" if hit else f"实际: {rs[:1]}")

print("\n" + "=" * 74)
print("独立验证 · 闸⑩ 上下游成对兼容（自己造的 fixture）")
print("=" * 74)
P = m.PairBinding
GOOD = dict(upstream_sha="deadbeef1234", current_sha="deadbeef1234",
            downstream_consumers=["A", "B"], downstream_tested=["A", "B"],
            pair_behavior_test=True)
ck(m.pairwise_compat(P(**GOOD), cfg)[0] is True, "已知【好】绑定 ⇒ PASS")
cj = [
    ("上游 sha 不匹配",         dict(current_sha="0000ffff9999"),                          "上游不绑定"),
    ("缺 upstream_sha",         dict(upstream_sha=""),                                    "缺 upstream_sha"),
    ("未声明下游",              dict(downstream_consumers=[], downstream_tested=[]),       "未声明"),
    ("下游只测了 1/2",          dict(downstream_tested=["A"]),                             "成对"),
    ("下游测了未声明的第三方",   dict(downstream_tested=["A", "B", "Z"]),                   None),  # 多余不算缺
    ("只测组件未测装配行为",     dict(pair_behavior_test=False),                            "装配后系统"),
    ("未提供 pair",             None,                                                     "未提供上下游绑定"),
]
for nm, patch, need in cj:
    p = None if patch is None else P(**{**GOOD, **patch})
    ok, rs, _ = m.pairwise_compat(p, cfg)
    if need is None:
        ck(ok is True, f"{nm} ⇒ 仍 PASS（多做不罚）")
    else:
        hit = (ok is False) and any(need in r for r in rs)
        ck(hit, f"{nm} ⇒ REJECT 且原因含「{need}」", "" if hit else f"实际: {rs[:1]}")

print("\n" + "=" * 74)
print("独立验证 · 向后兼容（旧签名调用不得改变旧判决）")
print("=" * 74)
tasks = [f"t{i}" for i in range(41)]
parent = set(tasks[:20])
c = m.Candidate("legacy", diff="+ 控制流改进", parent_solved=parent, child_solved=set(tasks[:23]),
                score=65.5, resolved=True, verified=True, d_score=3.0, d_cost=0.15)
dual = m.DualReport(deltas={"adopt": 3.0, "in_domain_heldout": 1.2, "ood": 0.8, "cross_model": 0.3})
reps = [61.0, 62.5, 60.8, 61.7, 62.0]
r_old = m.evaluate(c, cfg, best_so_far=62.5, baseline_scores=reps, dual=dual)
ck(r_old["admit"] is True, "旧格式调用（无 judge/pair）⇒ 仍 ADMIT")
ck("judge_reliability" not in r_old and "pairwise_compat" not in r_old, "兼容模式下不注入新键（输出契约未变）")
r_new = m.evaluate(c, m.GateConfig(strict_admission=True), best_so_far=62.5, baseline_scores=reps, dual=dual)
ck(r_new["admit"] is False, "严格模式 ⇒ 缺两栏即拒")
ck(r_new["judge_reliability"] is False and r_new["pairwise_compat"] is False, "严格模式下降级为 False 并给出原因")
r_both = m.evaluate(c, m.GateConfig(strict_admission=True), best_so_far=62.5, baseline_scores=reps, dual=dual,
                    judge=J(**BASE), pair=P(**GOOD))
ck(r_both["admit"] is True, "严格模式 + 两栏齐备 ⇒ ADMIT")

print("\n" + "=" * 74)
print(f"独立验证判决: {'✅ 全部命中预期' if not FAILS else '❌ ' + str(len(FAILS)) + ' 条未命中: ' + str(FAILS)}")
print("=" * 74)
raise SystemExit(0 if not FAILS else 1)
