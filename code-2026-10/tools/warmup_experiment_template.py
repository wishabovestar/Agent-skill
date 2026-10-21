#!/usr/bin/env python3
"""warmup_experiment_template.py — 「冷加载首调用丢弃」实验模板（可直接改参数复用）。

回答一个问题：**首调用是否与稳态一致**，以及哪种修法最便宜。
三个臂，每个臂都在**卸载重载**之后跑（保证是冷启动）：

  raw       : 不预热，直接连打 R 次          —— 首调用大概率跑偏
  prefill   : 首调用前用同一 prompt 跑 1 token 灌 KV 前缀（生产用法，后续零额外开销）
  stable    : 每次取样前都先用同一 prompt 丢一次（最稳，但每次双份 prompt 计算）

判据：稳态 = 第 2..R 次里占多数的指纹；PASS = 第 1 次指纹 == 稳态指纹。
退出码：0 = prefill 臂首调用已稳定；3 = prefill 仍不稳（判据可失败）。

用法：
  python warmup_experiment_template.py                       # 默认 7b / R=4
  python warmup_experiment_template.py --model qwen2.5:1.5b --runs 6
  python warmup_experiment_template.py --arms raw,prefill     # 只跑指定臂
"""
import argparse
import collections
import io
import json
import sys
import time

sys.path.insert(0, "D:/hermes/analysis")
from local_fallback_warmup import WarmClient, fingerprint, unload  # noqa: E402

PROBE = "写一段 60 词左右的英文，说明为什么可复现性在机器学习实验中很重要。"


def run_arm(arm, model, runs, num_ctx, num_predict):
    unload(model)                      # 强制冷加载
    c = WarmClient(model, num_ctx=num_ctx, discard=0, temperature=0.0, verbose=False)
    rows = []
    for i in range(runs):
        t0 = time.time()
        if arm == "prefill":
            txt, d = c.generate_prefilled(PROBE, num_predict=num_predict, num_ctx=num_ctx)
        elif arm == "stable":
            txt, d = c.generate_stable(PROBE, num_predict=num_predict, num_ctx=num_ctx)
        else:
            txt, d = c.generate(PROBE, num_predict=num_predict, num_ctx=num_ctx)
        rows.append({
            "i": i, "fp": fingerprint(txt), "eval_count": d.get("eval_count"),
            "done_reason": d.get("done_reason"), "chars": len(txt),
            "load_ms": d.get("load_duration", 0) // 1000000,
            "ms": round((time.time() - t0) * 1000),
        })
    tail = [r["fp"] for r in rows[1:]] or [rows[0]["fp"]]
    steady = collections.Counter(tail).most_common(1)[0][0]
    return {
        "arm": arm, "rows": rows, "steady": steady,
        "first_ok": rows[0]["fp"] == steady,
        "distinct": len({r["fp"] for r in rows}),
        "prefill_calls": c.prefill_calls,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:7b-ctx64k")
    ap.add_argument("--runs", type=int, default=4)
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--num-predict", type=int, default=200)
    ap.add_argument("--arms", default="raw,prefill,stable")
    ap.add_argument("--out", default="D:/hermes/analysis/_warmup_experiment")
    a = ap.parse_args()

    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    out = []
    for arm in arms:
        r = run_arm(arm, a.model, a.runs, a.num_ctx, a.num_predict)
        out.append(r)
        print("[%-7s] first_ok=%s distinct=%d/%d prefill_calls=%d steady=%s"
              % (arm, r["first_ok"], r["distinct"], a.runs, r["prefill_calls"], r["steady"]), flush=True)
        for row in r["rows"]:
            print("   i=%d fp=%s eval=%s %s chars=%d load_ms=%d %dms"
                  % (row["i"], row["fp"], row["eval_count"], row["done_reason"],
                     row["chars"], row["load_ms"], row["ms"]), flush=True)

    pre = next((r for r in out if r["arm"] == "prefill"), None)
    ts = time.strftime("%Y%m%d_%H%M%S")
    io.open("%s_%s.json" % (a.out, ts), "w", encoding="utf-8").write(
        json.dumps({"model": a.model, "runs": a.runs, "probe": PROBE, "arms": out},
                   ensure_ascii=False, indent=1))
    io.open("%s_%s.txt" % (a.out, ts), "w", encoding="utf-8", newline="").write(
        "model=%s runs=%d\n" % (a.model, a.runs) + "\n".join(
            "%-7s first_ok=%s distinct=%d prefill_calls=%d" % (r["arm"], r["first_ok"], r["distinct"], r["prefill_calls"])
            for r in out) + "\n")
    print("wrote %s_%s.json/.txt" % (a.out, ts))

    if pre is None:
        print("skip: 未跑 prefill 臂，无判据")
        return 0
    if pre["first_ok"]:
        print("PASS prefill 臂首调用 == 稳态")
        return 0
    print("FAIL prefill 臂首调用仍偏离稳态（fp=%s vs steady=%s）"
          % (pre["rows"][0]["fp"], pre["steady"]))
    return 3


if __name__ == "__main__":
    sys.exit(main())
