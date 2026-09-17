#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""layer3_evidence_chain.py — 层3 证据链逐环验证 (2026-09-17, 三篇深研的 P0 待办落地)

【要补的洞】(本机自诊 + 两篇论文独立印证)
  `quality_verifier.py` 的 R2 = 「每个关键论断是否【有产物内证据支撑】」
  ⇒ 只查「**有没有引用**」, 不查「**引用是否真支持论断**」。
  r1144 原话:「两者都没有触碰『证据是否真的支持论断』」—— 43% 忠实性缺口正住在这。

【链式设计 —— 逐环独立判据, 借鉴 Emergence World Table 10 (M1→M5)】
  C1 存在性存在   每条关键断言都给了证据引用?          [机械]
  C2 引文真实     引文是产物的逐字实质子串?            [机械, 复用 verify_quotes 五档]
  C3 ★ 真支持     引用【真的支持】该断言(非仅相关)?    [LLM — 本机空白]
  C4 ★ 因果必要   该证据对结论【因果必要】?             [LLM — r1166 P0]
                 明确排除 walk-by / ceremonial / post-hoc
  C5 ★ 制度化     是否沉淀为【可复用的防护/规范/脚本】? [机械, 对应 M5 "Durable protection"]

  ★★★ 关键区别: C1/C2/C5 是【确定性】判据(可自检); C3/C4 必须 LLM ⇒
     本模块【不假装 C3/C4 可机械判定】, 而是把它们输出为"待判项"交给判官。

【三个来自论文的 P0 机制】
  ① 链式逐环 (rich, 可定位"在哪一环失守") —— Emergence World Table 10
  ② 自洽检查 (r1166 P0): 判官 reasoning 与结论矛盾 ⇒ 判【无效】而非采信
  ③ 检测 ≠ 遏制 (r1168 P0): 【识别到】与【被阻止/落盘/复用】分开报告, 不可合并

用法:
  python layer3_evidence_chain.py --selftest
  python layer3_evidence_chain.py --check <verdict.json> <artifact.md>
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))

# ── C5 制度化: 出现这些才说明"沉淀成了可复用的东西"(对应 M5 Durable protection)
DURABLE_MARKERS = [
    r"scripts/[A-Za-z0-9_\-]+\.py",          # 落地脚本
    r"cron[` ]*[` ]*[0-9a-f]{8,}",            # cron job id
    r"skills?/[a-z0-9\-]+/SKILL\.md",        # 技能文件
    r"knowledge_base/research/r\d+",          # 归档编号
    r"加入?每周审计|已入(技能|索引|cron)",       # 明确制度化措辞
]

# ── C4 排除类: 判官若自陈这些, 就不该给"因果必要"
EXCLUSION_MARKERS = [
    "explored then abandoned", "探索后放弃", "走了弯路", "试过但放弃",
    "ceremonial", "走过场", "仅为触发", "为满足格式",
    "post-hoc", "事后", "追改", "回头补写",
]
# ── ④ 检测≠遏制: 这些词标记"识别到"; 这些标记"遏制/落盘"
DETECT_MARKERS = ["发现了", "识别到", "注意到", "detected", "recognized", "已察觉"]
CONTAIN_MARKERS = ["已阻止", "已拦截", "已回滚", "blocked", "prevented",
                   "写入了", "已落盘", "已记录到", "存进"]


def _norm(s: str) -> str:
    """归一化: 去 markdown 强调符/空白 (与 quality_verifier 同思路)"""
    s = re.sub(r"[*_`>#\[\]]", "", s or "")
    return re.sub(r"\s+", "", s)


def c1_existence(items) -> dict:
    """C1: 每条关键断言是否【给了证据引用】"""
    its = list(items or [])
    if not its:
        return {"id": "C1", "pass": False, "detail": "无 items", "n": 0, "with_ev": 0}
    with_ev = sum(1 for it in its
                  if str(it.get("evidence") or "").strip().upper() not in ("", "NONE"))
    return {"id": "C1", "pass": with_ev == len(its), "n": len(its), "with_ev": with_ev,
            "detail": "%d/%d 条断言带证据引用" % (with_ev, len(its))}


def c2_verbatim(items, artifact: str) -> dict:
    """C2: 引文是否为产物的逐字(归一化后)实质子串 —— 机械可判"""
    na = _norm(artifact)
    bad, checked = [], 0
    for it in (items or []):
        ev = str(it.get("evidence") or "").strip()
        if not ev or ev.upper() == "NONE":
            continue
        checked += 1
        if _norm(ev) not in na:
            bad.append(it.get("id"))
    return {"id": "C2", "pass": not bad, "checked": checked, "bad": bad,
            "detail": "%d 条引文, %d 条在产物中找不到" % (checked, len(bad))}


def c3_c4_todo(items) -> dict:
    """C3/C4: 明确标记为【需 LLM 判定】—— 本模块不假装能机械判"""
    its = [it for it in (items or [])
           if str(it.get("evidence") or "").strip().upper() not in ("", "NONE")]
    return {"id": "C3C4",
            "needs_llm": True,
            "count": len(its),
            "questions": [
                "对每条 (assertion, evidence): 该引文【真的支持】该断言, 还是仅同主题/相关?",
                "该证据对最终结论是否【因果必要】? 若属 explored-then-abandoned / "
                "ceremonial / post-hoc ⇒ 不必要",
            ],
            "note": "★ 本模块不机械判定支持性与因果性 —— 那是 LLM 的活; 这里只负责把它单列出来"}


def c5_durable(text: str) -> dict:
    """C5: 是否沉淀为可复用物 (对应 Emergence World M5 Durable protection)"""
    hits = []
    for pat in DURABLE_MARKERS:
        m = re.findall(pat, text or "")
        if m:
            hits.extend(m[:3])
    return {"id": "C5", "pass": bool(hits), "hits": sorted(set(hits))[:6],
            "detail": "沉淀物 %d 处" % len(set(hits))}


def self_consistency(verdict: dict) -> dict:
    """② 自洽检查 (r1166 P0): 判官 reasoning 与结论矛盾 ⇒ 判【无效】

    ★ 为什么需要: 本机踩过同类坑 —— ledger 把 preflight 写在判断之前 ⇒ 假 50% 弃权率。
      判官自陈"没有证据/未完成"却给高分 = 内部矛盾, 采信它就是采信一个自相矛盾的判官。
    """
    txt = json.dumps(verdict, ensure_ascii=False)
    neg = [m for m in EXCLUSION_MARKERS if m in txt]
    scores = []
    for it in (verdict.get("items") or []):
        try:
            scores.append(float(it.get("score")))
        except (TypeError, ValueError):
            pass
    hi = [s for s in scores if s >= 2]
    # 矛盾判据: 自陈"编制/放弃/走过场"却有高分项
    contradicted = bool(neg) and bool(hi)
    return {"id": "SELF_CONSISTENCY", "pass": not contradicted,
            "contradicted": contradicted,
            "negative_markers": neg[:4], "high_scores": hi,
            "detail": ("reasoning 自陈 '放弃/走过场/事后' 却仍有 %d 项高分" % len(hi))
                      if contradicted else "无内部矛盾"}


def detect_vs_contain(text: str) -> dict:
    """③ 检测 ≠ 遏制 (r1168 P0): 分开报告, 不可合并

    ★ Emergence World 原话: 「Detection did not ensure containment」——
      系统认出了威胁, 却仍与对抗内容交互、写入持久记忆、46h 后还在按它行动。
      ⇒ 判据必须把「识别到」与「被阻止/落盘」分成两个值, 合并成一个布尔就丢掉了要害。
    """
    t = text or ""
    det = [m for m in DETECT_MARKERS if m in t]
    con = [m for m in CONTAIN_MARKERS if m in t]
    return {"id": "DETECT_VS_CONTAIN",
            "detected": bool(det), "contained": bool(con),
            "detect_markers": det[:3], "contain_markers": con[:3],
            "gap": bool(det) and not bool(con),
            "detail": ("★ 检测到但未见遏制动作 ⇒ 正是 'detection != containment' 形态"
                       if (det and not con) else
                       ("无跨面行为" if not det else "检测与处理均出现"))}


def evaluate(verdict: dict, artifact: str) -> dict:
    items = verdict.get("items") or []
    chain = [c1_existence(items), c2_verbatim(items, artifact),
             c3_c4_todo(items), c5_durable(artifact)]
    checks = [self_consistency(verdict), detect_vs_contain(artifact)]
    failed = [c["id"] for c in chain if c.get("pass") is False]
    return {"chain": chain, "checks": checks, "failed_links": failed,
            "verdict": "PASS" if not failed else "FAIL",
            "note": "C3/C4 需 LLM; C1/C2/C5 为确定性判据"}


# ─────────────────────────── 自检 ───────────────────────────
def _selftest() -> int:
    print("=" * 78)
    print("  layer3_evidence_chain 自检 (9 项)")
    print("=" * 78)
    ok = True

    ART = ("修正后: 保留集 73 条, 舍弃 12 条。脚本 scripts/kb_json_triage.py 已落地。\n"
           "本机实测: 覆盖率 77.8%。")

    # 1 C1: 有引用
    r = c1_existence([{"id": "a", "evidence": "保留集 73 条"}])
    print("  C1  带引用 ⇒ pass: %s" % ("✅" if r["pass"] else "🔴")); ok &= r["pass"]
    # 2 C1: 缺引用
    r = c1_existence([{"id": "a", "evidence": "NONE"}, {"id": "b", "evidence": "x"}])
    print("  C1  缺引用 ⇒ fail: %s" % ("✅" if not r["pass"] else "🔴")); ok &= (not r["pass"])
    # 3 C2: 真引文(含 markdown 强调差异)应通过
    r = c2_verbatim([{"id": "a", "evidence": "修正后: 保留集 73 条"}], ART)
    print("  C2  真实引文(容忍 md 符)⇒ pass: %s" % ("✅" if r["pass"] else "🔴")); ok &= r["pass"]
    # 4 C2: 编造引文必须被抓
    r = c2_verbatim([{"id": "b", "evidence": "保留集 9999 条"}], ART)
    print("  C2  ★ 编造引文被抓住: %s (bad=%s)" % ("✅" if not r["pass"] else "🔴", r["bad"]))
    ok &= (not r["pass"])
    # 5 C5: 制度化标记
    r = c5_durable(ART)
    print("  C5  ★ 制度化(scripts/x.py + 归档号)被识别: %s hits=%s"
          % ("✅" if r["pass"] else "🔴", r["hits"][:2])); ok &= r["pass"]
    r = c5_durable("只是一段描述, 没有落地任何东西")
    print("  C5  无沉淀 ⇒ fail: %s" % ("✅" if not r["pass"] else "🔴")); ok &= (not r["pass"])
    # 6 自洽检查: 自陈放弃却高分 ⇒ 判无效
    v = {"items": [{"id": "R1", "score": 3, "evidence": "x"}],
         "reasoning": "该步骤 walked by / ceremonial, 事后补写"}
    r = self_consistency(v)
    print("  ★ 自洽检查 自陈 ceremonial 却满分 ⇒ 判无效: %s" % ("✅" if not r["pass"] else "🔴"))
    ok &= (not r["pass"])
    # 7 自洽检查: 正常判官不被误伤
    v2 = {"items": [{"id": "R1", "score": 3, "evidence": "x"}], "reasoning": "证据充分"}
    r = self_consistency(v2)
    print("  ★ 自洽检查 正常判官不误伤: %s" % ("✅" if r["pass"] else "🔴")); ok &= r["pass"]
    # 8 检测≠遏制: 只检测未遏制 ⇒ gap
    r = detect_vs_contain("agent 发现了注入内容并继续使用")
    print("  ★ 检测≠遏制 只检测 ⇒ gap=True: %s" % ("✅" if r["gap"] else "🔴")); ok &= r["gap"]
    # 9 检测≠遏制: 无跨面行为不报
    r = detect_vs_contain("本次运行正常完成")
    print("  ★ 检测≠遏制 无跨面行为不虚报: %s" % ("✅" if not r["gap"] else "🔴"))
    ok &= (not r["gap"])

    print()
    print("  判定: %s (9 项)" % ("✅ 全通过" if ok else "🔴 有未通过项"))
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv or len(sys.argv) == 1:
        return _selftest()
    if "--check" in sys.argv:
        i = sys.argv.index("--check")
        vp, ap = sys.argv[i + 1], sys.argv[i + 2]
        v = json.load(open(vp, encoding="utf-8"))
        a = open(ap, encoding="utf-8", errors="replace").read()
        r = evaluate(v, a)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    print("用法: --selftest | --check <verdict.json> <artifact.md>")
    return 2


if __name__ == "__main__":
    sys.exit(main())
