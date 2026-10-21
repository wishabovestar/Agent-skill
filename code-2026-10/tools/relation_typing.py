# -*- coding: utf-8 -*-
"""relation_typing.py — 关系谓词抽取（cortexmem 边类型的「第二通道」）

为什么有这个文件
──────────────────────────────────────────────────────────────────────
2026-10-18 定位到：四个 profile 的 `cortexmem.py::_link_entities` 只有一处建边，
字面就是 `{"from": nid, "to": eid, "type": "mentions"}`（mybot/qqbot3 L132，
qqbot2/qqbot5 L123）。图里 18651 条边 100% 是 `mentions` ⇒ D12 判「关系图退化成
词袋」。这不是数据被压平，是**写者根本没有关系抽取阶段**。

本件补的正是那一段：给定「记忆正文 + 尾实体名」，从**同句/邻近句**里的谓词线索
判定关系类型；无线索则老实退回 `mentions`（不得编造关系）。

设计纪律
──────────────────────────────────────────────────────────────────────
1. ★ 宁可漏判不可错判：无谓词线索 ⇒ `mentions`；谓词与实体不同句 ⇒ confidence 降级。
2. ★ 类型集合是【小闭集】，每条带中文线索字面（可逐条复核）。
3. ★ 纯函数、无 I/O、无副作用 ⇒ 可被写者内联调用，也可离线扫全图（--scan 只读）。
4. ★ `--selftest` 必须能失败：含 1 条「不支持 ⇒ REFUTES 而非 SUPPORTS」的反向陷阱。

用法
──────────────────────────────────────────────────────────────────────
  python relation_typing.py --selftest
  python relation_typing.py --classify "…正文…" --entity "LiSiC"
  python relation_typing.py --scan <profile>/knowledge_base/cortexmem/state.json [--top 10]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys

MENTIONS = "mentions"

# ⚠️ 精度优先（2026-10-18 校准结论）：只保留「谓词本身就断言关系」的字面。
#   被剔除的低精度词：包含/包括/分为/使用/采用/基于/利用/对比/相比/之后/随后/属于/表明/支持
#   —— 实测（qqbot3 18773 边抽样）这些词 ~60% 命中来自表格/流程描述，属伪关系。
_RULES: list[tuple[str, re.Pattern]] = [
    ("REFUTES",      re.compile(r"(不支持|否认|反驳|推翻|证伪)")),
    ("CAUSES",       re.compile(r"(导致|引起|造成|致使|使得)")),
    ("COMPOSED_OF",  re.compile(r"(由[^。；]{0,24}(组成|构成))")),
    ("SUPPORTS",     re.compile(r"(验证|证实|证明)")),
    ("CONTRASTS",    re.compile(r"(优于|劣于|高于|低于)")),
]

_SENT_SPLIT = re.compile(r"[。；;！!？?\n]+")


def _sents(text: str) -> list[str]:
    out = []
    for s in _SENT_SPLIT.split(text or ""):
        s = s.strip()
        if not s:
            continue
        # 表格行/代码行不承载「关系」，只制造伪命中（校准实测：'包含'/'导致' 多来自表格）
        if s.count("|") >= 2 or s.startswith(("#", "```", ">", "-", "*", "|")):
            continue
        out.append(s)
    return out


PROXIMITY = 24   # 谓词与实体名之间的「间隔字数」上限（超过即视为同句不同事）


def _near(s: str, ent: str, m: re.Match) -> bool:
    """实体与谓词之间的间隔字数 ≤ PROXIMITY ⇒ 视为同一命题（允许主谓宾被定语拉长）。"""
    best = None
    start = 0
    while True:
        i = s.find(ent, start)
        if i < 0:
            break
        j = i + len(ent)
        if m.end() <= i:                 # 谓词在实体前
            d = i - m.end()
        elif m.start() >= j:             # 谓词在实体后
            d = m.start() - j
        else:                            # 重叠（如「由…SiC…组成」）
            d = 0
        best = d if best is None else min(best, d)
        start = i + 1
    return best is not None and best <= PROXIMITY


def classify(text: str, entity: str) -> tuple[str, float, str]:
    """→ (rel_type, confidence, evidence)

    confidence: 0.9 = 谓词与实体【同句且≤16字】；0.4 = 谓词在正文但实体不在邻近；
                0.0 = 无线索 ⇒ mentions
    evidence  : 命中的谓词字面（mentions 时为空串），便于逐条复核
    """
    if not text:
        return MENTIONS, 0.0, ""
    ent = (entity or "").strip()
    if ent.startswith("实体:"):
        ent = ent[3:]
    sents = _sents(text)
    if ent:
        for s in sents:
            if ent not in s:
                continue
            for name, rx in _RULES:
                m = rx.search(s)
                if m and _near(s, ent, m):
                    return name, 0.9, m.group(0)
        for s in sents:                      # 同句但距离远 ⇒ 降级，不采纳
            if ent in s:
                for name, rx in _RULES:
                    m = rx.search(s)
                    if m:
                        return name, 0.4, m.group(0)
    else:
        for s in sents:
            for name, rx in _RULES:
                m = rx.search(s)
                if m:
                    return name, 0.9, m.group(0)
    for s in sents:                          # 兜底：只在「存活句」里找谓词（表格/代码行已剔除）
        for name, rx in _RULES:
            m = rx.search(s)
            if m:
                return name, 0.4, m.group(0)
    return MENTIONS, 0.0, ""


# ═══════════════ 离线扫描（只读；用于校准与迁移前评估）═══════════════
def scan(state_path: str, top: int = 10, samples: int = 6, min_conf: float = 0.0) -> dict:
    d = json.load(open(state_path, encoding="utf-8"))
    nodes = d.get("nodes", {}) or {}
    edges = d.get("edges", []) or []
    out = collections.Counter()
    confs = collections.Counter()
    by_type_samples: dict[str, list] = collections.defaultdict(list)
    for e in edges:
        src = nodes.get(e.get("from"), {}) or {}
        dst = nodes.get(e.get("to"), {}) or {}
        text = src.get("content") or ""
        ent = (dst.get("content") or "").replace("实体:", "")
        rt, cf, ev = classify(text, ent)
        if cf < min_conf:            # 只在「可采纳阈值」上统计，避免把噪声算进收益
            rt, cf, ev = MENTIONS, 0.0, ""
        out[rt] += 1
        confs[cf] += 1
        if rt != MENTIONS and len(by_type_samples[rt]) < samples:
            by_type_samples[rt].append({"edge": [e.get("from"), e.get("to")],
                                        "type": rt, "conf": cf, "evidence": ev,
                                        "entity": ent, "text": text[:120]})
    return {"edges": len(edges), "distribution": dict(out.most_common()),
            "confidence": dict(confs.most_common()),
            "typed": sum(v for k, v in out.items() if k != MENTIONS),
            "samples": by_type_samples}


# ═══════════════ 自检（必须能失败）═══════════════
def selftest() -> int:
    cases = [
        # (正文, 实体, 期望类型, 期望可采纳(conf>=0.9), 说明)
        ("冷辊温度过低导致极片粘辊", "冷辊", "CAUSES", True, "因果"),
        ("实验验证了 SiC 涂层可以提高附着力", "SiC", "SUPPORTS", True, "验证"),
        ("现有证据不支持该模型在 200°C 下稳定", "模型", "REFUTES", True, "否定陷阱：不支持 ⇒ REFUTES"),
        ("涂层由 Cu 层和 SiC 层组成", "SiC", "COMPOSED_OF", True, "组成"),
        ("烘箱温度高于设定值 5°C", "烘箱", "CONTRASTS", True, "比较"),
        ("极片宽度 300mm，面密度 12mg/cm2", "极片", "mentions", False, "负向对照：无谓词 ⇒ 不得编造关系"),
        ("| 验证 | 通过 |\n| 包含 | 是 |", "验证", "mentions", False, "表格陷阱：表格行不算关系"),
        ("烘箱温度记录在工艺卡片第二页并且已经由当班工程师逐项复核签字确认无误，"
         "随后在交接班记录里发现导致偏差的原因", "烘箱", "CAUSES", False,
         "距离陷阱：谓词离实体 >24 字 ⇒ 降级不采纳"),
        ("采用红外烘箱替代热风循环", "红外烘箱", "mentions", False,
         "刻意牺牲召回：'采用' 已从精度集剔除（实测伪关系占比高）"),
    ]
    bad = 0
    for text, ent, want, want_adopt, why in cases:
        got, cf, ev = classify(text, ent)
        adopt = cf >= 0.9
        ok = (got == want) and (adopt == want_adopt)
        if not ok:
            bad += 1
        print(f"  {'PASS' if ok else 'FAIL'}  want={want:<12}adopt={want_adopt!s:<6} "
              f"← got {got:<12}conf={cf} adopt={adopt!s:<6} ev={ev!r}  [{why}]")
    print(f"\n自测汇总: PASS={len(cases) - bad} FAIL={bad}")
    if bad:
        print("❌ 自检不过线")
        return 1
    print("✅ 自检过线（含否定陷阱 / 无谓词 / 表格 / 距离 / 低精度词剔除 5 条负向对照）")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--classify")
    ap.add_argument("--entity", default="")
    ap.add_argument("--scan")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--min-conf", type=float, default=0.0)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.classify is not None:
        print(classify(a.classify, a.entity))
        return 0
    if a.scan:
        r = scan(a.scan, top=a.top, min_conf=a.min_conf)
        print(f"边={r['edges']} ｜ 被赋予关系类型={r['typed']} ｜ 分布={r['distribution']}")
        print(f"置信度分布={r['confidence']}")
        for t, rows in r["samples"].items():
            print(f"\n[{t}] 样本 {len(rows)} 条")
            for s in rows:
                print(f"  conf={s['conf']} ev={s['evidence']!r} ent={s['entity']!r}")
                print(f"    text={s['text']!r}")
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
