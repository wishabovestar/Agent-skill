#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_product_template.py —— 通用「多因子乘积闸」（任一因子为 0 ⇒ 总分归零）

演自哪篇
────────
arXiv 2610.18052v1《Can Agents Forget When Asked? A Benchmark for Memory
Unlearning in LLM Agents》(基准名 Bemula)。

其总分是**乘积式**（原文 Eq.5，逐字）：
    Score = FA × UG ,  FA = √(FE·AR) ,  UG = √(PR·RLA)
原文对「乘积」的判词（原文陈述，逐字）：
    "Because the score is a product, a zero on any of the four metrics zeroes the
     total. A system that deletes everything scores no better than one that
     forgets nothing, and a system that can no longer learn similar facts also
     scores zero."
其「有效正确性」口径（原文陈述，逐字）：
    "The effective correctness z̃_i = z_i ∧ c_i conditions every efficacy,
     preservation, and attack question on the control version."

本件把上述**结构**落成一个可配置、可复用、可失败的闸：
    因子 = (名称, 判据函数, 证据来源, 权重形态)
    总分 = Π_i  f_i ^ exponent_i        exponent = FORMS[form] · weight
    硬不变量：任一 f_i == 0  ⇒  总分 == 0（并有断言守卫，见 judge()）

纪律（逐条可核）
────────
1. ★ 每个因子必须自带**可失败的判据**。配置期用「反例输入」实测：若判据在反例上仍判通过
   ⇒ 判**该因子配置本身报错**（FactorConfigError），不进入裁决。判据不可失败 = 假闸。
2. ★ 缺证据 ⇒ 默认 **fail-closed 判 0**（失败出声）：读不到 ≠ 报正常。可显式改
   on_missing_evidence='undecidable' 走 exit 2，但默认不放行。
3. ★ 强制归零只用于**负向对照**，且必须**高声报出**被归零的因子名（不许静默）。
4. ★ 纯 stdlib、确定性、零模型调用、零网络。
5. ★ 只新建/只读；run-real 只输出到 stdout，不写库、不落台账、不改既有文件。

用法
────
    python -u gate_product_template.py selftest        # 自检（正向全绿 + 三类负向对照）
    python -u gate_product_template.py audit           # 静态自审
    python -u gate_product_template.py who             # 拓扑说明
    python -u gate_product_template.py bemula-check     # 用原文字面输入复现 Eq.5 公式结构
    python -u gate_product_template.py run-real [--json F] [--leak-cap N]
退出码：0=总分非零(admit) / 1=总分 0(reject，高声) / 2=不可判定 / 3=因子配置报错
side_effects: [仅 selftest 写 _gate_product_selftest.log；其余只读或仅 stdout]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

BASE = Path('D:/hermes/analysis')
SELFTEST_LOG = BASE / '_gate_product_selftest.log'
GATE_VERSION = 'gate_product/1.0'
PAPER = 'arXiv 2610.18052v1 (Bemula), Eq.5'

# ── 权重形态 ⇒ 指数系数（出处：Bemula Eq.5 的 √ 即 geomean；非论文处皆标「本仓设计」）──
FORMS = {
    'linear': 1.0,    # f^weight           本仓设计（通过率/上限类默认）
    'geomean': 0.5,   # f^(weight·0.5)     Bemula Eq.5：FA=√(FE·AR)、UG=√(PR·RLA)
}
ON_MISSING_POLICIES = ('fail', 'undecidable')
DEFAULT_ON_MISSING = 'fail'          # 失败出声纪律：缺证据默认判 0，不判通过
VALID_STATUS = ('pass', 'zero', 'missing_evidence', 'forced_zero')

EXIT = {'admit': 0, 'reject': 1, 'undecidable': 2, 'config_error': 3}


class FactorConfigError(ValueError):
    """因子配置非法（含「判据不可失败」）—— 配置期即报错，绝不进入裁决。"""


# ═════════════════════ 因子规格 ═════════════════════
@dataclass
class FactorSpec:
    name: str
    criterion: Callable[[dict], dict]     # payload -> {'value': float|None, 'passed': bool, 'detail': str}
    evidence_key: str                     # 证据来源：payload 里必须存在的键
    evidence_desc: str                    # 证据来源的人类说明
    weight: float = 1.0
    form: str = 'linear'
    falsify_input: dict = field(default_factory=dict)   # 反例输入：必须把判据打到「失败」
    on_missing_evidence: str = DEFAULT_ON_MISSING

    def exponent(self) -> float:
        return FORMS[self.form] * float(self.weight)


# ═════════════════════ 判据工厂（每个都自带可失败点）═════════════════════
def crit_z_and_c(z_field: str = 'arm1_reps', c_field: str = 'arm0_reps') -> Callable:
    """(a) 双条件口径 z ∧ c：两条件都满足才计 1，否则 0；取逐 rep 平均。

    出处：Bemula「有效正确性」原文 —— "z̃_i = z_i ∧ c_i"（原文陈述）。
    z = 处置臂(被评)正确性；c = 配对对照探针正确性。可失败点：c 全对而 z 全错 ⇒ 值 0。
    """
    def f(p: dict) -> dict:
        items = p.get('items') or []
        n_hit = n_tot = miss_c = 0
        for it in items:
            z, c = it.get(z_field), it.get(c_field)
            if c is None:
                miss_c += 1
                continue
            if z is None:
                continue
            for zr, cr in zip(z, c):
                n_tot += 1
                if int(bool(zr)) and int(bool(cr)):
                    n_hit += 1
        if n_tot == 0:
            return {'value': None, 'passed': False,
                    'detail': f'可判 rep 数=0（条目 {len(items)}，缺对照字段 {c_field} 者 {miss_c}）'}
        v = n_hit / n_tot
        return {'value': v, 'passed': v > 0,
                'detail': f'z∧c 命中 {n_hit}/{n_tot} rep（条目 {len(items)}，缺对照 {miss_c}）'}
    return f


def crit_all_pass_rate(z_field: str = 'arm1_reps') -> Callable:
    """(b) 通过率类：一条目须「全部 rep 都对」才算通过（跨问题取 ∧），再对条目取平均。

    出处形态：Bemula「request pass rate」的 ∧ 严格性（原文陈述：a request passes only
    when all of its questions ... are correct）。可失败点：任一条目含 0 ⇒ 该条目不通过；
    全条目不通过 ⇒ 值 0。
    """
    def f(p: dict) -> dict:
        items = p.get('items') or []
        if not items:
            return {'value': None, 'passed': False, 'detail': '无 items'}
        npass = 0
        for it in items:
            z = it.get(z_field) or []
            if z and all(int(bool(x)) for x in z):
                npass += 1
        v = npass / len(items)
        return {'value': v, 'passed': v > 0,
                'detail': f'全 rep 通过条目 {npass}/{len(items)}'}
    return f


def crit_exposure_ceiling(cap_key: str = 'leak_cap',
                          z_field: str = 'arm1_reps', c_field: str = 'arm0_reps') -> Callable:
    """(c) 上限/暴露类：暴露量（对照正确却处置失败 = c∧¬z 的 rep 数）相对预算 cap 的余量。

    值 = max(0, 1 − 暴露/cap)。可失败点：暴露 ≥ cap ⇒ 值 0。缺 cap ⇒ None（缺证据）。
    出处：本仓设计（把 Bemula「任一因子为 0 则总分归零」的硬顶语义落成可有上限的因子）。
    """
    def f(p: dict) -> dict:
        cap = p.get(cap_key)
        if cap is None:
            return {'value': None, 'passed': False, 'detail': f'缺 {cap_key}（暴露预算）'}
        try:
            cap = float(cap)
        except Exception:
            return {'value': None, 'passed': False, 'detail': f'{cap_key} 非数值'}
        if cap <= 0:
            return {'value': None, 'passed': False, 'detail': f'{cap_key}≤0 无意义'}
        items = p.get('items') or []
        exp = 0
        for it in items:
            z, c = it.get(z_field) or [], it.get(c_field) or []
            for zr, cr in zip(z, c):
                if int(bool(cr)) and not int(bool(zr)):
                    exp += 1                      # 对照正确却处置失败 ⇒ 暴露/泄漏
        v = max(0.0, 1.0 - exp / cap)
        return {'value': v, 'passed': v > 0,
                'detail': f'暴露 {exp}/{cap} ⇒ 上限因子 {v:.4f}'}
    return f


def crit_rate(key: str) -> Callable:
    """标量比率因子（Bemula FE/AR/PR/RLA 各类）：证据 = payload[key]，须在 [0,1]。

    可失败点：key=0 ⇒ 判据失败。
    """
    def f(p: dict) -> dict:
        if key not in p or p[key] is None:
            return {'value': None, 'passed': False, 'detail': f'缺 {key}'}
        try:
            v = float(p[key])
        except Exception:
            return {'value': None, 'passed': False, 'detail': f'{key} 非数值'}
        if not (0.0 <= v <= 1.0):
            return {'value': None, 'passed': False, 'detail': f'{key}={v} 越界 [0,1]'}
        return {'value': v, 'passed': v > 0, 'detail': f'{key}={v}'}
    return f


def crit_always_pass(*_a, **_k) -> Callable:
    """★ 反面教具：恒真判据（永不失败）。仅用于 selftest 负向对照 C，不得进生产配置。"""
    return lambda p: {'value': 1.0, 'passed': True, 'detail': '恒真（教具，不可失败）'}


# ═════════════════════ 配置校验（判据不可失败 ⇒ 报错）═════════════════════
def validate_specs(specs: list) -> bool:
    """跑配置期自证：每个因子必须在反例输入上**干净失败**，否则配置本身报错。"""
    errs = []
    names = [sp.name for sp in specs]
    if not specs:
        errs.append('未配置任何因子 ⇒ 空闸（乘积恒 1，等于没有闸）')
    if len(set(names)) != len(names):
        errs.append(f'因子名重复：{names}')
    for sp in specs:
        if sp.form not in FORMS:
            errs.append(f'因子 {sp.name}: 未知权重形态 {sp.form!r}（可选 {sorted(FORMS)}）')
        if not callable(sp.criterion):
            errs.append(f'因子 {sp.name}: criterion 不可调用')
        if not sp.evidence_key:
            errs.append(f'因子 {sp.name}: 缺证据来源（evidence_key 为空）')
        if sp.on_missing_evidence not in ON_MISSING_POLICIES:
            errs.append(f'因子 {sp.name}: 未知缺证据策略 {sp.on_missing_evidence!r}')
        fz = sp.falsify_input
        if not isinstance(fz, dict) or not fz:
            errs.append(f'因子 {sp.name}: 未提供反例输入 ⇒ 无法证明判据可失败 ⇒ 配置报错')
            continue
        try:
            out = sp.criterion(fz)
        except Exception as e:
            errs.append(f'因子 {sp.name}: 反例输入上判据抛异常（未干净失败）'
                        f'{type(e).__name__}: {e} ⇒ 配置报错')
            continue
        if not isinstance(out, dict) or 'passed' not in out:
            errs.append(f'因子 {sp.name}: 判据返回格式非法（缺 passed）')
            continue
        if out.get('passed') or (out.get('value') is not None and float(out['value']) > 0):
            errs.append(f'因子 {sp.name}: ★判据不可失败★ —— 反例输入上仍判通过'
                        f'（value={out.get("value")}, passed={out.get("passed")}）⇒ 该因子配置本身报错')
    if errs:
        raise FactorConfigError('；'.join(errs))
    return True


# ═════════════════════ 裁决主体 ═════════════════════
def judge(payload: dict, specs: list, *, force_zero: Optional[set] = None) -> dict:
    """乘积裁决。返回 dict(verdict, total, factors[], zeroing_factors[], ...)。

    硬不变量：任一因子 value==0 ⇒ total==0（末尾断言守卫）。
    """
    force_zero = set(force_zero or ())
    rows, total, zeroing, undec = [], 1.0, [], []
    for sp in specs:
        name, status = sp.name, None
        if name in force_zero:
            v, status, detail = 0.0, 'forced_zero', '★强制归零（负向对照）⇒ 高声报出'
        elif not (sp.evidence_key in payload and payload.get(sp.evidence_key) is not None):
            if sp.on_missing_evidence == 'fail':
                v, status = 0.0, 'missing_evidence'
                detail = f'缺证据「{sp.evidence_key}」⇒ fail-closed 判 0（失败出声）'
            else:
                v, status = None, 'missing_evidence'
                detail = f'缺证据「{sp.evidence_key}」⇒ 不可判定（不改判通过）'
        else:
            try:
                out = sp.criterion(payload)
            except Exception as e:
                out = {'value': None, 'passed': False,
                       'detail': f'判据异常 {type(e).__name__}: {e}'}
            v = out.get('value')
            detail = out.get('detail', '')
            if v is None:
                if sp.on_missing_evidence == 'fail':
                    v, status = 0.0, 'missing_evidence'
                    detail = f'{detail} ⇒ fail-closed 判 0（失败出声）'
                else:
                    status = 'undecidable'
            else:
                v = float(v)
                status = 'pass' if v > 0 else 'zero'
        exp = sp.exponent()
        contrib = None if v is None else v ** exp
        if v == 0.0 and name not in zeroing:
            zeroing.append(name)
        if v is None and name not in undec:
            undec.append(name)
        if v is not None and total != 0.0:
            total *= contrib
        if v == 0.0:
            total = 0.0
        rows.append({'name': name, 'form': sp.form, 'weight': sp.weight, 'exponent': exp,
                     'evidence_key': sp.evidence_key, 'evidence_desc': sp.evidence_desc,
                     'value': v, 'status': status, 'detail': detail, 'contrib': contrib})
    if undec:
        verdict = 'undecidable'
    elif total == 0.0:
        verdict = 'reject'
    else:
        verdict = 'admit'
    invariant_ok = (not zeroing) or (total == 0.0)
    if not invariant_ok:                    # 不变量守卫：理论上不可达，可达即闸坏
        raise AssertionError('乘积不变量被破坏：有因子为 0 但总分非 0')
    if total == 0.0 and zeroing:
        reason = '总分归零 ← 因子：' + '、'.join(zeroing)
    elif verdict == 'undecidable':
        reason = '不可判定 ← 因子：' + '、'.join(undec)
    else:
        reason = '全部因子 >0，乘积非零'
    return {'schema': GATE_VERSION, 'paper': PAPER, 'verdict': verdict,
            'total': total, 'zeroing_factors': zeroing, 'undecidable_factors': undec,
            'factors': rows, 'zero_invariant_ok': invariant_ok, 'reason': reason}


# ═════════════════════ 人类可读裁决表 ═════════════════════
def render_table(res: dict) -> str:
    w = (12, 8, 6, 8, 8, 9, 18, 40)
    head = ('因子', '形态', '权重', '指数', '值', '状态', '证据源', '备注')
    def line(cs): return '| ' + ' | '.join(str(c).ljust(w[i]) for i, c in enumerate(cs)) + ' |'
    out = [line(head), '|' + '|'.join('-' * (w[i] + 2) for i in range(len(w))) + '|']
    for r in res['factors']:
        out.append(line((r['name'], r['form'], r['weight'], f"{r['exponent']:.3g}",
                         'None' if r['value'] is None else f"{r['value']:.4f}",
                         r['status'], r['evidence_key'], r['detail'][:40])))
    out.append('')
    out.append(f"总分 = Π f^e = {res['total']:.6f}   verdict = {res['verdict'].upper()}"
               f"   ({res['reason']})")
    if res['zeroing_factors']:
        out.append('★ 归零因子（高声）：' + '、'.join(res['zeroing_factors']))
    return '\n'.join(out)


# ═════════════════════ 预设与真实数据 ═════════════════════
def default_specs() -> list:
    """三件内建示例因子：(a) 双条件口径 z∧c (b) 通过率类 (c) 上限/暴露类。"""
    return [
        FactorSpec('z_and_c', crit_z_and_c(), 'items',
                   '逐条目 arm1_reps(=z) 与 arm0_reps(=c) 配对 rep（Bemula z̃=z∧c 口径）',
                   weight=1.0, form='geomean',
                   falsify_input={'items': [{'id': 'F', 'arm0_reps': [1, 1], 'arm1_reps': [0, 0]}],
                                  'reps': 2}),
        FactorSpec('all_pass_rate', crit_all_pass_rate(), 'items',
                   '逐条目 arm1_reps 全对才算通过（RPR 式 ∧ 严格性）',
                   weight=1.0, form='linear',
                   falsify_input={'items': [{'id': 'F', 'arm1_reps': [1, 0]}]}),
        FactorSpec('exposure_ceiling', crit_exposure_ceiling(), 'leak_cap',
                   '暴露 = 对照正确却处置失败的 rep 数；预算 leak_cap（本仓设计）',
                   weight=1.0, form='linear',
                   falsify_input={'leak_cap': 2,
                                  'items': [{'id': 'F', 'arm0_reps': [1, 1], 'arm1_reps': [0, 0]}]}),
    ]


def bemula_preset() -> list:
    """把 Bemula Eq.5 的四个叶因子落成配置：Score = Π FE^½·AR^½·PR^½·RLA^½ = FA·UG。"""
    mk = lambda k, d: FactorSpec(k, crit_rate(k), k, d, weight=1.0, form='geomean',
                                 falsify_input={k: 0.0})
    return [mk('FE', 'forgetting efficacy（Bemula Eq.3 S_eff 平均有效正确率）'),
            mk('AR', 'attack robustness（Bemula Eq.3 攻击套件平均）'),
            mk('PR', 'preservation（Bemula Eq.3 S_pres 平均有效正确率）'),
            mk('RLA', 'relearning accuracy（Bemula Eq.3 S_rl 平均有效正确率）')]


def payload_from_schema_b(path: os.PathLike, leak_cap: float) -> dict:
    """schema b：{reps, k, items[].arm0_reps/arm1_reps} → 闸 payload。

    arm 语义（【我的判断/推断】，非论文陈述）：本仓 eb_shrink_ledger.jsonl 记
    source="json schema(b): _eb11_reps_sample.json"、M0_hit/M1_hit，且默认探针对为
    probe_M0_baseline.log vs probe_M1_surgery.log ⇒ arm0=对照臂(M0_baseline)、
    arm1=处置臂(M1_surgery)。样本文件本身未声明 arm 语义。
    """
    p = Path(path)
    d = json.loads(p.read_text(encoding='utf-8'))
    return {'items': d['items'], 'reps': d.get('reps'), 'k': d.get('k'),
            'leak_cap': leak_cap, 'source': str(p),
            'arm_semantics': 'arm0=对照臂(M0_baseline) / arm1=处置臂(M1_surgery)'
                             '（依 eb_shrink_ledger.jsonl；样本文件未声明）'}


# ═════════════════════ 自检（非恒真：正向全绿 + 三类负向对照）═════════════════════
_SYN = {
    'items': [
        {'id': 'S1', 'arm0_reps': [1, 1, 1], 'arm1_reps': [1, 1, 1]},
        {'id': 'S2', 'arm0_reps': [1, 1, 1], 'arm1_reps': [1, 1, 0]},
        {'id': 'S3', 'arm0_reps': [1, 0, 1], 'arm1_reps': [1, 1, 1]},
        {'id': 'S4', 'arm0_reps': [1, 1, 1], 'arm1_reps': [1, 1, 1]},
    ],
    'reps': 3, 'leak_cap': 10.0,
}


class _Tee:
    """同时写 stdout 与自检日志。"""
    def __init__(self, fh):
        self.fh = fh

    def p(self, s: str = ''):
        print(s)
        self.fh.write(s + '\n')
        self.fh.flush()


def selftest() -> int:
    SELFTEST_LOG.parent.mkdir(parents=True, exist_ok=True)
    fh = SELFTEST_LOG.open('w', encoding='utf-8')
    t = _Tee(fh)
    t.p(f"=== gate_product_template 自检（非恒真）===  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    t.p(f"版本 {GATE_VERSION}   演自 {PAPER}   日志 {SELFTEST_LOG}")
    checks = []
    specs = default_specs()

    # ① 配置期自证：三因子判据在各自反例上都能失败
    try:
        validate_specs(specs)
        checks.append(('① 配置校验通过（三因子判据在反例上均能失败）', True, 'FactorConfigError 未触发'))
    except FactorConfigError as e:
        checks.append(('① 配置校验通过（三因子判据在反例上均能失败）', False, f'意外报错：{e}'))

    # ② 正向全绿：总分非零 ⇒ admit
    r = judge(_SYN, specs)
    t.p('')
    t.p(render_table(r))
    checks.append(('② 正向全绿：总分非零 ⇒ admit', r['verdict'] == 'admit' and r['total'] > 0,
                   f"total={r['total']:.6f} verdict={r['verdict']}"))
    # 各因子手算对照（非恒真：值与手算一致）
    exp_z = (3 + 2 + 2 + 3) / 12
    exp_p = 3 / 4
    exp_c = 1 - 1 / 10
    manual = exp_z ** 0.5 * exp_p ** 1.0 * exp_c ** 1.0
    checks.append(('②b 各因子值与手算一致（z∧c=10/12, 通过率=3/4, 上限=0.9）',
                   math.isclose(r['factors'][0]['value'], exp_z, rel_tol=1e-9)
                   and math.isclose(r['factors'][1]['value'], exp_p, rel_tol=1e-9)
                   and math.isclose(r['factors'][2]['value'], exp_c, rel_tol=1e-9)
                   and math.isclose(r['total'], manual, rel_tol=1e-9),
                   f"z∧c={r['factors'][0]['value']:.4f} pass={r['factors'][1]['value']:.4f} "
                   f"ceil={r['factors'][2]['value']:.4f} total={r['total']:.6f} manual={manual:.6f}"))

    # ③ 负向对照 A：强制某因子为 0 ⇒ 总分 0 且高声报出该因子
    rA = judge(_SYN, specs, force_zero={'all_pass_rate'})
    t.p('')
    t.p('── 负向对照 A：强制 all_pass_rate = 0 ──')
    t.p(render_table(rA))
    checks.append(('③ 负向A 强制归零 ⇒ total=0 + 高声报出因子', 
                   rA['total'] == 0.0 and rA['verdict'] == 'reject'
                   and 'all_pass_rate' in rA['zeroing_factors'],
                   f"total={rA['total']} zeroing={rA['zeroing_factors']} reason={rA['reason']}"))

    # ④ 负向对照 B：缺证据（payload 无 leak_cap）⇒ fail-closed 判 0 且高声报出
    synB = {k: v for k, v in _SYN.items() if k != 'leak_cap'}
    rB = judge(synB, specs)
    t.p('')
    t.p('── 负向对照 B：缺证据（payload 无 leak_cap）──')
    t.p(render_table(rB))
    checks.append(('④ 负向B 缺证据 ⇒ fail-closed total=0 + 报出 exposure_ceiling',
                   rB['total'] == 0.0 and rB['verdict'] == 'reject'
                   and 'exposure_ceiling' in rB['zeroing_factors'],
                   f"total={rB['total']} zeroing={rB['zeroing_factors']}"))

    # ⑤ 负向对照 C：判据不可失败 ⇒ 配置本身报错并点名
    bad = FactorSpec('never_fails', crit_always_pass(), 'items', '恒真教具', weight=1.0,
                     form='linear', falsify_input={'items': [{'id': 'x', 'arm1_reps': [0]}]})
    named = False
    msg = ''
    try:
        validate_specs([specs[0], bad])
    except FactorConfigError as e:
        msg = str(e)
        named = 'never_fails' in msg and '判据不可失败' in msg
    checks.append(('⑤ 负向C 判据不可失败 ⇒ 配置报错并点名 never_fails', named, msg or '未报错（假闸）'))

    # ⑥ 乘积不变量：逐个因子强制置 0，总分都必须为 0
    inv_ok, inv_detail = True, []
    for sp in specs:
        rr = judge(_SYN, specs, force_zero={sp.name})
        inv_ok = inv_ok and rr['total'] == 0.0 and rr['zero_invariant_ok'] and sp.name in rr['zeroing_factors']
        inv_detail.append(f"{sp.name}→{rr['total']:.1f}")
    checks.append(('⑥ 乘积不变量：任一因子 0 ⇒ 总分 0（逐因子实测）', inv_ok, ' '.join(inv_detail)))

    # ⑦ 权重形态真被读进去（翻转实验：上限因子 linear→geomean 应改变总分）
    alt = default_specs()
    alt[2].form = 'geomean'
    r7 = judge(_SYN, alt)
    checks.append(('⑦ 权重形态真生效（exposure_ceiling linear→geomean 改变总分）',
                   not math.isclose(r7['total'], r['total'], rel_tol=1e-9),
                   f"linear={r['total']:.6f} geomean={r7['total']:.6f}"))

    # ⑧ Bemula Eq.5 公式结构复现（原文输入，本模板计算；非论文新结论）
    bp = {'FE': 0.268, 'AR': 0.276, 'PR': 0.733, 'RLA': 0.982}
    rb = judge(bp, bemula_preset())
    expected = math.sqrt(0.268 * 0.276) * math.sqrt(0.733 * 0.982)
    checks.append(('⑧ Bemula Eq.5 结构复现：Π FE^½·AR^½·PR^½·RLA^½ = √(FE·AR)·√(PR·RLA)',
                   math.isclose(rb['total'], expected, rel_tol=1e-9),
                   f"gate={rb['total']:.6f} direct={expected:.6f}"))
    rbz = judge({'FE': 0.0, 'AR': 0.276, 'PR': 0.733, 'RLA': 0.982}, bemula_preset())
    checks.append(('⑧b 原文「任一因子 0 ⇒ 总分 0」在四叶因子上成立（FE=0 ⇒ 0）',
                   rbz['total'] == 0.0, f"total={rbz['total']} zeroing={rbz['zeroing_factors']}"))

    t.p('')
    ok = all(v for _, v, _ in checks)
    for name, v, d in checks:
        t.p(('  ✅ ' if v else '  ❌ ') + name + '  —  ' + str(d))
    t.p(f"⇒ 自检 {'PASS ✓' if ok else 'FAIL ✗'}（{sum(1 for _, v, _ in checks if v)}/{len(checks)}）"
        f"  日志={SELFTEST_LOG}")
    fh.close()
    return 0 if ok else 1


# ═════════════════════ 静态自审 ═════════════════════
def audit() -> dict:
    src = Path(__file__).read_text(encoding='utf-8')
    _MODEL_LIBS = ('requ' 'ests', 'ur' 'llib', 'open' 'ai', 'oll' 'ama', 'ht' 'tp')
    checks = [
        ('出处标注：Bemula Eq.5 与原文乘积判词',
         'arXiv 2610.18052' in src and 'zeroes the' in src and 'total' in src, '源头可查'),
        ('硬不变量：任一因子 0 ⇒ 总分 0（含断言守卫）',
         'if v == 0.0:' in src and 'total = 0.0' in src and 'AssertionError' in src, '不变量+守卫'),
        ('配置期判据可失败性实测（反例驱动）',
         "if out.get('passed')" in src and '判据不可失败' in src, 'FactorConfigError 点名'),
        ('缺证据 fail-closed（默认判 0，不判通过）',
         "DEFAULT_ON_MISSING = 'fail'" in src and 'fail-closed 判 0' in src, '读不到≠报正常'),
        ('强制归零高声报出（不静默）',
         "'forced_zero', '★强制归零" in src and "'zeroing_factors'" in src, '点名因子'),
        ('权重形态表在册（linear/geomean）',
         "'linear': 1.0" in src and "'geomean': 0.5" in src, 'FORMS 表'),
        ('纯确定性（无模型/网络调用）',
         not any(re.search(r'\b' + lib + r'\b', src) for lib in _MODEL_LIBS), 'stdlib only'),
        ('只读/只 stdout：run-real 不写库不落台账',
         'run-real 只输出到 stdout' in src, 'side_effects 声明'),
    ]
    return {'checks': [f'{"✅" if ok else "❌"} {n} — {d}' for n, ok, d in checks],
            'all_ok': all(ok for _, ok, _ in checks)}


def who() -> int:
    print(f'gate_product_template —— 通用「多因子乘积闸」（版本 {GATE_VERSION}）')
    print(f'  演自      : {PAPER}')
    print('  乘积      : 总分 = Π f_i^exponent_i ；任一 f_i==0 ⇒ 总分==0（断言守卫）')
    print(f'  形态      : {FORMS}（geomean 出处=Bemula Eq.5 的 √）')
    print(f'  缺证据    : 默认 {DEFAULT_ON_MISSING}（fail-closed 判 0，失败出声）')
    print('  内建因子  : z∧c 双条件口径 / all_pass_rate 通过率 / exposure_ceiling 上限暴露')
    print('  退出码    : 0=非零 / 1=归零 / 2=不可判定 / 3=因子配置报错')
    return 0


def bemula_check() -> int:
    """用原文字面输入（Table 1）复现 Eq.5 公式结构。输入=原文，输出=本模板计算。"""
    # 原文陈述：Bemula Table 1, backbone GPT-5.6-Luna 行（FE/PR/RLA/AR 与 Score 均照抄原文）
    rows = [
        ('Full Context', 26.8, 27.6, 73.3, 98.2, 23.1),
        ('Naive RAG',    14.7, 12.9, 67.3, 71.1,  9.5),
        ('LangMem',      37.9, 25.6, 20.0, 78.9, 12.4),
        ('Mem0',          8.5,  4.7, 80.0, 77.2,  4.9),
        ('A-MEM',        33.0, 24.7, 59.3, 88.6, 20.7),
        ('LightMem',     17.9, 18.0, 88.0, 80.7, 15.1),
    ]
    specs = bemula_preset()
    print('Bemula Eq.5 公式结构复现（输入=原文字面 Table 1；输出=本模板计算）')
    print('Score = Π FE^½·AR^½·PR^½·RLA^½ = √(FE·AR)·√(PR·RLA) = FA·UG')
    print(f"{'系统':<13}{'FE':>6}{'AR':>6}{'PR':>6}{'RLA':>6}{'计算Score':>11}{'原文Score':>10}{'差':>7}")
    n_exact = 0
    for name, fe, ar, pr, rla, paper in rows:
        bp = {'FE': fe / 100, 'AR': ar / 100, 'PR': pr / 100, 'RLA': rla / 100}
        r = judge(bp, specs)
        got = r['total'] * 100
        diff = got - paper
        n_exact += int(abs(round(got, 1) - paper) < 1e-9)
        print(f'{name:<13}{fe:>6.1f}{ar:>6.1f}{pr:>6.1f}{rla:>6.1f}{got:>11.2f}{paper:>10.1f}{diff:>+7.2f}')
    print(f'⇒ 四舍五入到 0.1 后与原文一致的行：{n_exact}/{len(rows)}'
          f'（不一致=原文可能的取整差异，非本仓结论）')
    print('〔我的判断〕本模板复现 Eq.5 的乘积结构；以上仅为公式复现，不含任何新结论。')
    return 0


def run_real(path: str, leak_cap: float, force_zero: str) -> int:
    payload = payload_from_schema_b(path, leak_cap)
    specs = default_specs()
    try:
        validate_specs(specs)
    except FactorConfigError as e:
        print(f'★ 因子配置报错（exit {EXIT["config_error"]}）：{e}', file=sys.stderr)
        return EXIT['config_error']
    fz = {s for s in force_zero.split(',') if s} or None
    res = judge(payload, specs, force_zero=fz)
    res['input'] = {'file': payload['source'], 'reps': payload['reps'], 'k': payload['k'],
                    'n_items': len(payload['items']), 'leak_cap': leak_cap,
                    'arm_semantics': payload['arm_semantics'],
                    'force_zero': sorted(fz) if fz else []}
    print(render_table(res))
    print()
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return EXIT[res['verdict']]


def main() -> int:
    ap = argparse.ArgumentParser(description='通用多因子乘积闸')
    ap.add_argument('cmd', choices=['selftest', 'audit', 'who', 'bemula-check', 'run-real'])
    ap.add_argument('--json', default=str(BASE / 'memory_ab' / '_eb11_reps_sample.json'))
    ap.add_argument('--leak-cap', type=float, default=8.0)
    ap.add_argument('--force-zero', default='')
    a = ap.parse_args()
    if a.cmd == 'selftest':
        return selftest()
    if a.cmd == 'audit':
        r = audit()
        for ln in r['checks']:
            print(ln)
        print('⇒', 'PASS ✓' if r['all_ok'] else 'FAIL ✗')
        return 0 if r['all_ok'] else 1
    if a.cmd == 'who':
        return who()
    if a.cmd == 'bemula-check':
        return bemula_check()
    return run_real(a.json, a.leak_cap, a.force_zero)


if __name__ == '__main__':
    raise SystemExit(main())
