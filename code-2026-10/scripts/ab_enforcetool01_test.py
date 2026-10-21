# -*- coding: utf-8 -*-
"""
AB-ENFORCETOOL-01 — 「提报有效性:有执行工具 vs 只开通道」
==========================================================
队列规格(总闸第二十一条): 举报/提报本身是否带来行为差异, 还是只有开了一个通道。

本机对应物 = cortexmem 写闸的三档 mode:
  A: off      → 无门(基线)
  B: log      → 只开通道: 判定并留台账, 但一律放行
  C: suppress → 有执行工具: 判定为拒收则真拦下

三档跑同一批带标签的候选, 测:
  ① 污染率  = 应拒项被真正写入的比例
  ② 误拦率  = 应放行项被拦下的比例
  ③ 判定层检出率/误报率(与 mode 无关, 门本身的判别力)

★ 正对照(必做): 用生产台账 _write_dropped.jsonl 里的真实拒收行回放,
  必须仍被判 reject —— 否则说明"检查器根本没命中已知在源数", 此时任何
  "降到 0" 都不能解读为有效(流程属性, 非数据属性)。

★ 隔离: 台账写入 CORTEXMEM_WG_DATA 指向的沙盒目录, 生产台账只读并在
  运行前后比对 sha256, 必须不变。
"""
import os, sys, json, hashlib, importlib.util
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GATE_PATH = r"D:/hermes/hermes-data/profiles/mybot/scripts/cortexmem_write_gate.py"
PROD_LEDGER = r"D:/hermes/hermes-data/profiles/mybot/knowledge_base/cortexmem/_write_dropped.jsonl"
SANDBOX = r"D:/hermes/data/ab_sandbox/enforce01"
OUT_JSON = r"D:/hermes/data/ab_enforce01_results.json"

os.makedirs(SANDBOX, exist_ok=True)
os.environ["CORTEXMEM_WG_DATA"] = SANDBOX
os.environ["CORTEXMEM_WG_SUMMARY"] = "off"      # 不要每写一行就往 stderr 打摘要
os.environ["CORTEXMEM_WRITE_GATE"] = "log"

if SANDBOX not in sys.path:
    sys.path.insert(0, SANDBOX)


def load_gate():
    spec = importlib.util.spec_from_file_location("cortexmem_write_gate", GATE_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def sha_file(p):
    try:
        return hashlib.sha256(open(p, "rb").read()).hexdigest()
    except Exception:
        return None


GATE = load_gate()
prod_before = sha_file(PROD_LEDGER)
print("gate loaded | DATA_DIR=%s" % GATE.DATA_DIR)
print("prod ledger sha256[:16] before = %s" % (prod_before or "-")[:16])

# ── 有效条目模板(must-admit): 三角色 + 四项齐全 ─────────────────────────
def good_meta(i, extra=None):
    m = {
        "dimension": "技术机制",
        "relevance_reason": "该条比较的是同一存储路径的参数差异, 维度直接相关 #%d" % i,
        "evidence": "R",
        "measure": "F1=0.6%02d" % (i % 100),
        "refutation": ["若在下一次独立复跑中 F1 未同向变化则本结论否证"],
        "source_ptr": ("sess-ab-%02d" % i, 3),
        "reopen_if": "若出现反向实测或样本规模翻倍后效应消失",
    }
    if extra:
        m.update(extra)
    return m


GOOD_TEXTS = [
    "写闸判定层在抑制模式下对缺来源指针的候选条目形成拦截, 复跑三次结论一致",
    "近重复阈值 0.70 在中文短句上的误报率需要按语料长度分档复核",
    "台账只记拒收行, 分母由计数器承载, 否则留存率会被自证刷成假过线",
    "压缩阶段边界 7/30 天在跨度 31.49 天的数据上优于 3/10/30 天 13.29pp",
    "同一 nid 全文相同应走升版分支, 不得计入门收益, 否则收益虚增",
    "证据等级仅 T 时允许入 L1 但禁升 L3/L4, 判定为上标未实证",
    "选择效应无法靠重跑消除, 必须报全分布或留出集重选才能归因",
    "噪声地板以下的分差不可计入涨点, 超噪带计数须同时报样本量",
    "评审自述推理与被评对象自述同源时, 该证据不构成独立观测",
    "跨模型迁移实验需要固定执行者之外的第二个模型做对照",
    "分块结构的数据不能当独立同分布抽样, 切分与验证都要按块进行",
    "把阈值从 1.0 降到 0.8 必须在隔离环境回归, 且记录误报绝对数",
]

# ── 应拒项(must-reject): 每项只缺一个要件, 便于归因 ──────────────────
def build_bad():
    bad = []
    fields = [
        ("dimension", "缺维度"),
        ("relevance_reason", "缺相关性理由"),
        ("evidence", "缺证据等级"),
        ("measure", "缺可测的量"),
        ("refutation", "缺反驳检查"),
        ("source_ptr", "缺来源指针"),
        ("reopen_if", "缺翻转条件"),
    ]
    base_texts = [
        "该候选断言在所有场景下都优于现状, 但未给出任何可测的量与来源指针",
        "该候选声称消除了全部误报, 但未说明在何种条件下该断言会被推翻",
    ]
    k = 0
    for fname, label in fields:
        for t in base_texts:
            k += 1
            meta = good_meta(k)
            meta.pop(fname, None)
            bad.append({"kind": "missing_" + fname, "label": label,
                        "text": "%s [#%02d]" % (t, k), "ntype": "semantic",
                        "meta": meta, "expect": "reject"})
    # 装配闸: 非法 ntype / 空文本
    bad.append({"kind": "assembly_ntype", "label": "非法节点类型",
                "text": "节点类型不在允许集内时无法装配进三层图, 属结构性不可写",
                "ntype": "speculative", "meta": good_meta(90), "expect": "reject"})
    bad.append({"kind": "assembly_empty", "label": "空内容",
                "text": "   ", "ntype": "semantic", "meta": good_meta(91), "expect": "reject"})
    return bad


def build_nodes():
    """近重复/前缀撞车用的已存在节点池。"""
    nodes = {}
    base = "写闸在抑制模式下拦截缺来源指针的条目, 复跑三次结论一致且误报为零"
    nodes["nid-base-01"] = {"content": base, "last_access": 1}
    nodes["nid-collide-01"] = {"content": "另一条与该候选前缀指纹相同但语义完全不同的记忆",
                               "last_access": 1}
    return nodes, base


def build_bad_dynamic(nodes, base):
    extra = []
    near = base.replace("复跑三次结论一致且误报为零", "复跑三次结论一致且误报接近零")
    extra.append({"kind": "near_duplicate", "label": "近重复 J>=0.70",
                  "text": near, "ntype": "semantic", "meta": good_meta(95),
                  "self_nid": "nid-new-near", "expect": "reject"})
    extra.append({"kind": "prefix_collision", "label": "前缀指纹撞车",
                  "text": "第三条内容, 与已存在的 nid-collide-01 全文不同",
                  "ntype": "semantic", "meta": good_meta(96),
                  "self_nid": "nid-collide-01", "expect": "reject"})
    return extra


def build_adversarial():
    """对抗子集: 四项俱全但语义空壳 —— 测的是"能否被 schema 满足所绕开"。
    这一组【不参与】执行有效性判定, 单独报, 否则就等于让门自证自己。
    """
    specs = [
        ("bogus_measure", "量填成'明显更好'(不可测)", {"measure": "明显更好"}),
        ("bogus_refutation", "反驳项填成'再找几篇支持'(非否证)", {"refutation": ["再找几篇支持"]}),
        ("wrong_dimension", "维度填事实断言但内容是流程决策", {"dimension": "事实断言"}),
        ("hollow_reason", "相关性理由填成'相关'空壳", {"relevance_reason": "相关"}),
    ]
    out = []
    for i, (kind, label, ov) in enumerate(specs):
        out.append({"kind": kind, "label": label,
                    "text": "候选条目声明其优于现状 %d, 并给出了看起来齐全的四项要件以通过闸" % i,
                    "ntype": "semantic", "meta": good_meta(70 + i, ov),
                    "self_nid": "nid-adv-%02d" % i, "expect": "reject"})
    return out


def run_item(item, nodes):
    allow, hint, info = GATE.before_add(
        item["text"], nodes, ntype=item["ntype"],
        self_nid=item.get("self_nid"), entry_meta=item["meta"])
    return {"allow": bool(allow), "verdict": info.get("verdict"),
            "channel": info.get("channel"), "mode": info.get("mode"),
            "judged": info.get("judged"), "error": info.get("error")}


def pct(a, b):
    return (100.0 * a / b) if b else 0.0


def main():
    nodes, base = build_nodes()
    bad = build_bad() + build_bad_dynamic(nodes, base)
    adv = build_adversarial()
    good = [{"kind": "good", "label": "齐全条目", "text": t, "ntype": "semantic",
             "meta": good_meta(i + 1), "expect": "admit", "self_nid": "nid-good-%02d" % i}
            for i, t in enumerate(GOOD_TEXTS)]

    # 正对照: 生产台账真实拒收行(只取 head 文本, 元数据留空 —— 与当初拒收时一致)
    real_rows = []
    try:
        for ln in open(PROD_LEDGER, encoding="utf-8"):
            ln = ln.strip()
            if ln:
                real_rows.append(json.loads(ln))
    except Exception as e:
        print("real ledger read err:", e)
    real_bad = [{"kind": "real_ledger:" + str(r.get("reason")), "label": "生产台账真实拒收行",
                 "text": (r.get("head") or "") + " [replay:%s]" % str(r.get("sha"))[:6],
                 "ntype": r.get("ntype") or "semantic", "meta": {},
                 "self_nid": "nid-replay-%02d" % i, "expect": "reject"}
                for i, r in enumerate(real_rows) if (r.get("head") or "").strip()]

    items = bad + good
    results = {}
    per_item = {}
    for mode in ("off", "log", "suppress"):
        os.environ["CORTEXMEM_WRITE_GATE"] = mode
        rows = []
        for it in items:
            r = run_item(it, nodes)
            r.update({"kind": it["kind"], "expect": it["expect"], "label": it["label"]})
            rows.append(r)
        # 正对照单独跑(台账回放行永远以空 meta 出现)
        real_rows_res = [run_item(it, nodes) for it in real_bad]
        adv_res = [run_item(it, nodes) for it in adv]
        results[mode] = {
            "n_bad": len(bad), "n_good": len(good), "n_adv": len(adv),
            "adv_admitted": sum(1 for r in adv_res if r["allow"]),
            "adv_blocked": sum(1 for r in adv_res if not r["allow"]),
            "bad_admitted": sum(1 for r, it in zip(rows, items)
                                if it["expect"] == "reject" and r["allow"]),
            "bad_blocked": sum(1 for r, it in zip(rows, items)
                               if it["expect"] == "reject" and not r["allow"]),
            "good_admitted": sum(1 for r, it in zip(rows, items) if it["expect"] == "admit" and r["allow"]),
            "good_blocked": sum(1 for r, it in zip(rows, items) if it["expect"] == "admit" and not r["allow"]),
            "judged_reject": sum(1 for r in rows if r["verdict"] == "reject"),
            "errors": sum(1 for r in rows if r["error"]),
            "real_control_n": len(real_bad),
            "real_control_rejected": sum(1 for r in real_rows_res if r["verdict"] == "reject"),
        }
        per_item[mode] = rows

    # 判定层(与 mode 无关, 取 suppress 那次)
    d = results["suppress"]
    det_rate = pct(d["bad_blocked"], d["n_bad"])
    fp_rate = pct(d["good_blocked"], d["n_good"])
    cont = {m: pct(results[m]["bad_admitted"], results[m]["n_bad"]) for m in results}
    fp = {m: pct(results[m]["good_blocked"], results[m]["n_good"]) for m in results}
    real_hit = pct(d["real_control_rejected"], d["real_control_n"]) if d["real_control_n"] else None
    gaming = pct(d["adv_admitted"], d["n_adv"])

    delta_channel = cont["off"] - cont["log"]          # 通道相对无门的降污染
    delta_tool = cont["log"] - cont["suppress"]        # 工具相对通道的降污染
    fp_cost = fp["suppress"] - fp["log"]

    # 台账按 mode 分组核对(证明各档确实以不同 action 落盘)
    led = {}
    try:
        p = os.path.join(SANDBOX, "_write_dropped.jsonl")
        if os.path.exists(p):
            for ln in open(p, encoding="utf-8"):
                ln = ln.strip()
                if not ln:
                    continue
                r = json.loads(ln)
                led.setdefault((r.get("mode"), r.get("action")), 0)
                led[(r.get("mode"), r.get("action"))] += 1
    except Exception as e:
        led["err"] = str(e)

    prod_after = sha_file(PROD_LEDGER)

    # 判定
    checks = []
    checks.append(("正对照命中(生产台账行仍判 reject)", real_hit is not None and real_hit >= 90.0,
                   "real_control_reject_rate=%.1f%% (n=%d)" % (real_hit or 0, d["real_control_n"])))
    checks.append(("通道相对无门降污染≈0(通道本身不改变结果)", abs(delta_channel) <= 1.0,
                   "Δ=%.1fpp" % delta_channel))
    checks.append(("工具有效性: 抑制档把可检出污染压到 0", cont["suppress"] <= 0.0,
                   "contamination suppress=%.1f%%" % cont["suppress"]))
    checks.append(("误拦代价可接受(齐全条目误拦<=0)", fp["suppress"] <= 0.0,
                   "FP suppress=%.1f%% (Δvs log %+.1fpp)" % (fp["suppress"], fp_cost)))
    checks.append(("生产台账未被写(sha256 不变)", prod_before == prod_after,
                   "%s vs %s" % ((prod_before or "-")[:12], (prod_after or "-")[:12])))
    passed = all(ok for _, ok, _ in checks)

    out = {
        "test": "AB-ENFORCETOOL-01",
        "title": "提报有效性: 有执行工具(suppress) vs 只开通道(log) vs 无门(off)",
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "gate_path": GATE_PATH, "sandbox": SANDBOX,
        "per_mode": results,
        "contamination_pct": cont, "false_block_pct": fp,
        "detection_rate_pct_bad_blocked": det_rate,
        "false_positive_rate_pct_good_blocked": fp_rate,
        "delta_channel_vs_off_pp": delta_channel,
        "delta_tool_vs_channel_pp": delta_tool,
        "fp_cost_pp": fp_cost,
        "real_control_reject_rate_pct": real_hit,
        "adversarial_n": d["n_adv"],
        "adversarial_pass_rate_pct": gaming,
        "ledger_by_mode": {"%s|%s" % k: v for k, v in led.items()},
        "checks": [{"name": n, "ok": o, "evidence": e} for n, o, e in checks],
        "verdict": "PASS" if passed else "FAIL",
        "note": "suppress 档只在本实验沙盒内生效; 生产 gate 默认仍为 log, 是否切换需用户确认。"
                "注意: bad 集按【缺失字段】构造, 检出率 100% 属构造性结果; adversarial 集才是语义判别力的度量。",
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    open(OUT_JSON, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))

    print("\n=== AB-ENFORCETOOL-01: channel vs tool ===")
    print("%-10s %10s %10s %10s %10s" % ("mode", "contam%", "FP%", "bad_blk", "good_blk"))
    for m in ("off", "log", "suppress"):
        r = results[m]
        print("%-10s %10.1f %10.1f %10d %10d" % (m, cont[m], fp[m], r["bad_blocked"], r["good_blocked"]))
    print("\nitems: bad=%d good=%d | detection=%.1f%% FP=%.1f%%"
          % (d["n_bad"], d["n_good"], det_rate, fp_rate))
    print("positive control (real ledger replays): %d/%d rejected (%.1f%%)"
          % (d["real_control_rejected"], d["real_control_n"], real_hit or 0))
    print("adversarial (schema-satisfying, semantics-empty): admitted %d/%d = %.1f%% -> gate gaming surface"
          % (d["adv_admitted"], d["n_adv"], gaming))
    print("delta: channel_vs_off=%.1fpp tool_vs_channel=%.1fpp fp_cost=%+.1fpp"
          % (delta_channel, delta_tool, fp_cost))
    print("ledger rows by (mode|action): %s" % out["ledger_by_mode"])
    print("prod ledger unchanged: %s" % (prod_before == prod_after))
    for n, o, e in checks:
        print("  [%s] %s — %s" % ("PASS" if o else "FAIL", n, e))
    print("\nVERDICT: %s -> %s" % (out["verdict"], OUT_JSON))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
