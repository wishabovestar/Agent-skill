#!/usr/bin/env python3
"""摘要保真度闸门 — 本地小模型当摘要器，埋 N 条事实，压缩后只凭摘要判分。

判据（可失败）：
  PASS = recall >= --threshold 且 misbind == 0
（echo 仅作诊断指标打印，不参与判定：实测所有组合均为 0.000，该条件从未触发）
  退出码：0 = PASS，3 = FAIL（不合格即出声，绝不静默通过）

为什么需要它：compaction 之后承接连续性的是「摘要」，不是原文。摘要丢标识符
不会报错，只会让后续问答静默错位取数（见 _fidelity_ab.txt：S1 把 12 个数值
一个不差全列了，但 ID↔值 绑定丢了，问答端取到邻居的值）。

用法：
  python summary_fidelity_gate.py                      # 默认 24 条 / strict / 阈 0.90
  python summary_fidelity_gate.py --n 48 --runs 3
  python summary_fidelity_gate.py --prompt naive --n 48 # 预期 FAIL（exit 3）
"""
import argparse
import http.client
import io
import json
import os
import random
import re
import sys
import time

HOST, PORT = "127.0.0.1", 11434


def _post(path, payload, timeout=600):
    body = json.dumps(payload).encode("utf-8")
    c = http.client.HTTPConnection(HOST, PORT, timeout=timeout)
    c.request("POST", path, body, {"Content-Type": "application/json"})
    raw = c.getresponse().read().decode("utf-8")
    c.close()
    return json.loads(raw)


def generate(model, prompt, system="", num_predict=900, num_ctx=16384, temperature=0.0):
    payload = {
        "model": model, "stream": False, "prompt": prompt, "system": system,
        "options": {"temperature": temperature, "num_ctx": num_ctx, "num_predict": num_predict},
    }
    if str(model).startswith("qwen3"):      # 思维链会吃光 num_predict，判分场景必须关
        payload["think"] = False
    d = _post("/api/generate", payload)
    return (d.get("response") or "").strip(), d


FILL = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma "
        "tau upsilon phi chi psi omega process buffer segment window channel offset gain drift "
        "批次 复核 记录 参数 采集 校准 走查 归档").split()


def build_corpus(n_facts, seed=11):
    """n_facts 条 ZX-nn 事实，均匀埋进 3*n_facts 轮对话，其余为填充词。"""
    rnd = random.Random(seed)
    facts = [("ZX-%02d" % i, "%0.1f" % (5 + i * 7.3)) for i in range(1, n_facts + 1)]
    n_turns = max(40, n_facts * 3)
    step = n_turns / float(n_facts)
    slots = {int(round(i * step)): facts[i] for i in range(n_facts)}
    turns = []
    for t in range(n_turns):
        body = " ".join(rnd.choice(FILL) for _ in range(40))
        if t in slots:
            f, v = slots[t]
            body += " 记录：校准常数 %s 的读数为 %s mmHg。" % (f, v)
        turns.append("[第%d轮] %s" % (t + 1, body))
    return "\n".join(turns), facts


def prompt_pairs(target_chars):
    return {
        "naive": "你是会议记录员。把多轮对话压缩成不超过 %d 字的中文要点摘要，供后续问答使用。" % (target_chars // 2),
        "strict": ("你是会议记录员。把多轮对话压缩成不超过 %d 字的中文要点摘要，供后续问答使用。"
                   "要求：凡出现形如 ZX-nn 的编号及其数值，必须成对逐条保留，写成「ZX-nn: 数值」；"
                   "不得合并、省略、改写数字，也不得只列数值而丢掉编号。" % target_chars),
        # 2026-10-21 新增：治标版——把「邻行干扰」的检索面压到最小
        "lined": ("你是会议记录员。把多轮对话压缩成中文要点摘要，供后续问答使用。\n"
                  "唯一格式要求（必须严格遵守）：\n"
                  "① 凡出现形如 ZX-nn 的编号及其读数，每条独占一行，格式固定为「ZX-nn: 数值」；\n"
                  "② 行内除该格式外不得写任何其它文字；\n"
                  "③ 编号必须按 ZX-01、ZX-02、ZX-03 … 单调升序逐行排列，不许跳号、不许乱序、不许重复；\n"
                  "④ 不得合并、省略、改写数字。\n"
                  "除上述编号行外，其余内容压缩成不超过 %d 字的普通中文要点。" % target_chars),
    }


SYS_QA = ("你只能依据给出的摘要回答问题，禁止使用摘要以外的知识。"
          "摘要里有该编号的读数就只输出数值本身（例如 47.3）；没有就只输出 UNKNOWN。")


def shingles(t, k=20):
    return {t[i:i + k] for i in range(0, max(0, len(t) - k + 1), k)}


def echo_ratio(summary, source):
    s = shingles(summary)
    if not s:
        return 1.0
    return len(s & shingles(source)) / float(len(s))


def _embed(model, texts):
    d = _post("/api/embed", {"model": model, "input": texts}, timeout=180)
    return d.get("embeddings") or []


def _cos(a, b):
    s = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return s / (na * nb + 1e-9)


def score_facts(model, summary, facts, num_ctx, client=None, judge=None):
    """判分。

    judge=None          → 用 model 自判（原行为）
    judge=("model", m)  → 换独立判分模型 m 做同一套 QA
    judge=("bge", m)    → 用 m（bge-m3）做检索式取数：把摘要切成行，按 query 取最相似行，
                          再从该行抽数；没有数值则记 UNKNOWN。与生成端完全解耦。
    """
    hits, wrong, unknown, empty = [], [], [], []
    lines = emb_lines = qemb = None
    if judge and judge[0] == "bge":
        lines = [l.strip() for l in summary.splitlines() if l.strip()]
        if not lines:
            lines = [summary]
        emb_lines = _embed(judge[1], lines)
        qemb = _embed(judge[1], ["%s 的读数" % f for f, _ in facts])
    id_lines = {}
    if judge and judge[0] == "exact":
        loose = {}
        for l in summary.splitlines():
            m = re.search(r"ZX-(\d\d)", l)
            if not m:
                continue
            k = m.group(1)
            loose.setdefault(k, l)
            if re.search(r"ZX-\d\d\s*[:：]\s*-?\d", l):   # 优先「ZX-nn: 数值」形态，避免命中前言
                id_lines.setdefault(k, l)
        for k, l in loose.items():
            id_lines.setdefault(k, l)
    for i, (f, v) in enumerate(facts):
        if judge and judge[0] == "exact":
            ln = id_lines.get(f[3:])
            ans = ln if ln else "UNKNOWN"
        elif judge and judge[0] == "bge":
            sims = [_cos(qemb[i], e) for e in emb_lines]
            best = max(range(len(sims)), key=lambda k: sims[k])
            ans = lines[best]
        else:
            q = "摘要：\n" + summary + "\n\n问题：%s 的读数是多少？" % f
            jm = judge[1] if judge else model
            if client is not None and judge is None:
                ans, _ = client.generate_prefilled(q, num_predict=24, num_ctx=num_ctx, system=SYS_QA)
            else:
                ans, _ = generate(jm, q, system=SYS_QA, num_predict=24, num_ctx=num_ctx)
        nums = re.findall(r"-?\d+\.?\d*", re.sub(r"ZX-\d\d", " ", ans))
        if not nums:
            if "UNKNOWN" in ans.upper():
                unknown.append(f)
            else:
                empty.append((f, ans[:40]))
        elif abs(float(nums[0]) - float(v)) < 0.05:
            hits.append(f)
        else:
            wrong.append((f, nums[0], v))
    return hits, wrong, unknown, empty


def lined_compliance(summary, n_facts):
    """lined 变体的格式合规检查：编号行数 == n、每行形如 ZX-nn: 数值、编号严格 ZX-01..ZX-nn 升序。"""
    rows = re.findall(r"(?m)^\s*(?:[-*·]\s*)?ZX-(\d\d)\s*[:：]\s*(-?\d+(?:\.\d+)?)", summary)
    ids = [int(a) for a, _ in rows]
    want = list(range(1, n_facts + 1))
    return {"lines": len(rows), "ascending": ids == want,
            "contiguous": ids == sorted(ids) and len(set(ids)) == len(ids),
            "ok": ids == want}


def run_once(model, variant, n_facts, target_chars, num_ctx, seed, client=None, judge=None):
    convo, facts = build_corpus(n_facts, seed=seed)
    sys_sum = prompt_pairs(target_chars)[variant]
    t0 = time.time()
    if client is not None:
        summary, meta = client.generate_prefilled("对话如下：\n" + convo,
                                                  num_predict=target_chars * 2,
                                                  num_ctx=num_ctx, system=sys_sum)
    else:
        summary, meta = generate(model, "对话如下：\n" + convo, system=sys_sum,
                                 num_predict=target_chars * 2, num_ctx=num_ctx)
    hits, wrong, unknown, empty = score_facts(model, summary, facts, num_ctx, client, judge)
    er = echo_ratio(summary, convo)
    rec = len(hits) / float(len(facts))
    return {
        "variant": variant, "n": len(facts), "model": model, "seed": seed,
        "judge": (judge[0] + ":" + judge[1]) if judge else "self",
        "judge_model": judge[1] if judge else model,
        "convo_chars": len(convo), "summary_chars": len(summary),
        "ratio": round(len(convo) / max(1, len(summary)), 2),
        "recall": round(rec, 4), "hit": len(hits), "misbind": len(wrong),
        "unknown": len(unknown), "empty": len(empty),
        "echo": round(er, 3), "ids_kept": len(set(re.findall(r"ZX-\d\d", summary))),
        "lined": lined_compliance(summary, len(facts)) if variant == "lined" else None,
        "elapsed_s": round(time.time() - t0, 1),
        "wrong": wrong[:8], "unknown_ids": unknown[:8], "empty_detail": empty[:4],
        "summary": summary,
    }


def verdict(r, threshold):
    fails = []
    if r["recall"] < threshold:
        fails.append("recall %.3f < %.3f" % (r["recall"], threshold))
    if r["misbind"] > 0:
        fails.append("misbind %d > 0（错位取数，最危险）" % r["misbind"])
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("FID_MODEL", "qwen2.5:7b"))
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--target", type=int, default=0, help="摘要字数上限，0=按 N 自动(22*N)")
    ap.add_argument("--threshold", type=float, default=0.90)
    ap.add_argument("--prompt", default="strict", choices=["naive", "strict", "lined", "both"])
    ap.add_argument("--judge-model", default="", help="独立判分模型；空=与摘要器同模型自判")
    ap.add_argument("--judge-kind", default="model", choices=["model", "bge", "exact"],
                    help="model=换模型做 QA；bge=bge-m3 稠密检索；exact=按编号逐行精确取数（纯解析，无模型）")
    ap.add_argument("--reuse", default="", help="复用已有 JSON 的摘要，只重跑判分")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--num-ctx", type=int, default=16384)
    ap.add_argument("--out", default="D:/hermes/analysis/_fidelity_gate")
    ap.add_argument("--warm", action="store_true",
                    help="走 WarmClient.generate_prefilled：同一 prompt 首调用前先 prefill（丢弃冷调用）")
    a = ap.parse_args()

    target = a.target or max(300, 22 * a.n)
    client = None
    if a.warm:
        sys.path.insert(0, "D:/hermes/analysis")
        from local_fallback_warmup import WarmClient
        client = WarmClient(a.model, num_ctx=a.num_ctx, discard=0, temperature=0.0)
    judge = (a.judge_kind, a.judge_model) if a.judge_model else None
    rows = []
    if a.reuse:
        src = json.load(io.open(a.reuse, encoding="utf-8"))
        seen = {}
        for res in src:
            v = res["variant"]
            r = seen.get(v, 0)
            seen[v] = r + 1
            seed = res.get("seed", 11 + r)
            _c, facts = build_corpus(res["n"], seed=seed)
            hits, wrong, unknown, empty = score_facts(res["model"], res["summary"], facts,
                                                      a.num_ctx, None, judge)
            res.update({"recall": round(len(hits) / float(len(facts)), 4), "hit": len(hits),
                        "misbind": len(wrong), "unknown": len(unknown), "empty": len(empty),
                        "judge": (judge[0] + ":" + judge[1]) if judge else "self",
                        "judge_model": judge[1] if judge else res["model"],
                        "wrong": wrong[:8], "unknown_ids": unknown[:8],
                        "empty_detail": empty[:4], "seed": seed,
                        "lined": lined_compliance(res["summary"], res["n"]) if v == "lined" else res.get("lined")})
            rows.append(res)
    else:
        variants = ["naive", "strict"] if a.prompt == "both" else [a.prompt]
        for v in variants:
            for r in range(a.runs):
                rows.append(run_once(a.model, v, a.n, target, a.num_ctx, seed=11 + r,
                                     client=client, judge=judge))

    bad = 0
    for res in rows:
        fails = verdict(res, a.threshold)
        res["fails"] = fails
        print("[%s r%d] N=%d judge=%s recall=%.3f (%d/%d) misbind=%d unknown=%d ids=%d echo=%.2f ratio=%.2fx summary=%dch %.1fs -> %s"
              % (res["variant"], res["seed"] - 10, res["n"], res.get("judge", "self"),
                 res["recall"], res["hit"], res["n"], res["misbind"],
                 res["unknown"], res["ids_kept"], res["echo"], res["ratio"],
                 res["summary_chars"], res["elapsed_s"],
                 "PASS" if not fails else "FAIL"), flush=True)
        if res.get("lined"):
            lc = res["lined"]
            print("    lined: 编号行=%d 升序=%s 连续=%s -> %s"
                  % (lc["lines"], lc["ascending"], lc["contiguous"], "OK" if lc["ok"] else "格式未达标"), flush=True)
        for f in fails:
            print("    ✗ " + f, flush=True)
        if res["wrong"]:
            print("    misbound: %s" % res["wrong"], flush=True)
        bad += 1 if fails else 0

    ts = time.strftime("%Y%m%d_%H%M%S")
    io.open("%s_%s.json" % (a.out, ts), "w", encoding="utf-8").write(
        json.dumps(rows, ensure_ascii=False, indent=1))
    txt = ["gate model=%s n=%d target=%d threshold=%.2f (echo 仅诊断，不参与判定)" % (
        a.model, a.n, target, a.threshold)]
    for r in rows:
        txt.append("%-7s recall=%.3f misbind=%d unknown=%d ids=%d echo=%.2f ratio=%.2fx %s" % (
            r["variant"], r["recall"], r["misbind"], r["unknown"], r["ids_kept"], r["echo"], r["ratio"],
            "PASS" if not r["fails"] else "FAIL(" + "; ".join(r["fails"]) + ")"))
    io.open("%s_%s.txt" % (a.out, ts), "w", encoding="utf-8", newline="").write("\n".join(txt) + "\n")
    print("wrote %s_%s.json/.txt" % (a.out, ts))
    if bad:
        print("GATE FAIL: %d/%d 组合不合格" % (bad, len(rows)))
        raise SystemExit(3)
    print("GATE PASS: %d/%d 组合合格" % (len(rows), len(rows)))


if __name__ == "__main__":
    main()
