"""离群定性探针：temp>0 下固定 seed 跑 N 次，判定分歧是「提前 EOS」还是「采样分支不同」。

对每次调用抓 done_reason / eval_count / eval_duration，并对离群文本与多数簇做前缀比对：
  · 离群是多数簇的真前缀 + done_reason=stop  ⇒ 提前 EOS（采样器提前抽到终止符）
  · 离群在中途某字符处就分叉                 ⇒ 走了另一条采样分支

用法：
  python det_outlier_probe.py --temperature 0.9 --runs 20 --out _det_outlier_t09
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import statistics
import time
import urllib.request

URL = "http://127.0.0.1:11434/api/generate"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
PROMPT = ("You are a deterministic test harness. Reply with exactly 30 words about why fixed "
          "seeds matter for reproducible ML experiments. No preamble.")


def gen(model, prompt, seed, temp, npred):
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"num_predict": npred, "seed": seed, "temperature": temp}}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with OPENER.open(req, timeout=300) as r:
        d = json.loads(r.read().decode())
    return d, time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:1.5b")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--temperature", type=float, default=0.9)
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--num-predict", type=int, default=60)
    ap.add_argument("--out", default="_det_outlier")
    a = ap.parse_args()

    rows = []
    for i in range(a.runs):
        d, wall = gen(a.model, PROMPT, a.seed, a.temperature, a.num_predict)
        txt = d.get("response", "")
        rows.append({
            "i": i, "hash": hashlib.sha256(txt.encode()).hexdigest()[:16], "len": len(txt),
            "done_reason": d.get("done_reason"), "eval_count": d.get("eval_count"),
            "eval_ms": round((d.get("eval_duration") or 0) / 1e6),
            "wall_s": round(wall, 2), "text": txt,
        })
    with io.open(a.out + ".jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["hash"], []).append(r)
    out = [f"model={a.model} temp={a.temperature} seed={a.seed} runs={a.runs} np={a.num_predict}",
           f"簇数={len(groups)}  各簇样本数={sorted((len(v) for v in groups.values()), reverse=True)}"]
    for h, v in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        ec = [r["eval_count"] for r in v]
        dr = sorted({str(r["done_reason"]) for r in v})
        out.append(f"  {h} x{len(v)} len={sorted({r['len'] for r in v})} "
                   f"eval_count={sorted(set(ec))} done_reason={dr}")

    # 前缀比对：把每簇的代表与非代表逐一比对
    reps = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    if len(reps) > 1:
        major = reps[0][1][0]["text"]
        for h, v in reps[1:]:
            for r in v:
                t = r["text"]
                off = next((k for k in range(min(len(major), len(t))) if major[k] != t[k]), None)
                if off is None:
                    rel = "「离群是多数簇的真前缀」⇒ 提前 EOS" if len(t) < len(major) else "「多数簇是离群的真前缀」"
                else:
                    rel = f"在第 {off} 字符分叉 ⇒ 另一条采样分支"
                out.append(f"  {h}#{r['i']} len={len(t)} eval_count={r['eval_count']} "
                           f"done_reason={r['done_reason']} :: {rel}")
    ecs = [r["eval_count"] for r in rows]
    out.append(f"eval_count 统计: min={min(ecs)} median={int(statistics.median(ecs))} max={max(ecs)} "
               f"（np={a.num_predict}；等于 np ⇒ 撞上限，小于 np 且有 stop ⇒ 自然结束）")
    out.append(f"done_reason 分布: {dict((str(k), sum(1 for r in rows if str(r['done_reason']) == str(k))) for k in {r['done_reason'] for r in rows})}")
    io.open(a.out + ".txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"wrote {a.out}.jsonl / {a.out}.txt")


if __name__ == "__main__":
    main()
