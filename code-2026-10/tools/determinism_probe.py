#!/usr/bin/env python3
"""determinism_probe — 复现 DeepInfer 的 M1/M2 实验：输出是否与「批次形状」无关。

设计（对应 DeepInfer README 的两条契约）：
  M1 batch-invariant: bit-identical results across batch composition
  M2 deterministic:   fixed seed + no speculation + batch-invariant

三个模式，逐个加压力：
  sequential  同请求串行 N 次            → 检出「同参不重复」的下界问题
  concurrent  同请求并发 N 次            → 服务端可能把它们拼进同一 batch
  mixed       目标请求 + K 个干扰请求并发 → 强制异质 batch（最接近真实负载）

判据（写死，能失败）：每个模式内 sha256(输出文本) 的**簇数 > 1 ⇒ FAIL，exit 3**
并给出首个分歧字符 offset，便于定位是采样还是 kernel 归约顺序。

用法：
  python determinism_probe.py --model qwen2.5:1.5b --runs 5
  python determinism_probe.py --model qwen2.5:7b --runs 5 --modes sequential,concurrent,mixed --decoys 3
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
import urllib.request

DEFAULT_PROMPT = (
    "You are a deterministic test harness. Reply with exactly 30 words about "
    "why fixed seeds matter for reproducible ML experiments. No preamble."
)


def _opener():
    # 明确绕过系统/环境代理：本地 Ollama 不应走隧道
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(model: str, prompt: str, *, seed: int, temperature: float, num_predict: int,
         base: str, timeout: int = 180) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"seed": seed, "temperature": temperature, "num_predict": num_predict},
    }
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(f"{base}/api/generate", data=data,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with _opener().open(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    body["_wall_s"] = round(time.perf_counter() - t0, 2)
    body["_prompt_sha"] = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    return body


def _run_parallel(jobs: list[dict], base: str, results: list, lock: threading.Lock):
    def worker(idx: int, j: dict) -> None:
        try:
            r = call(j["model"], j["prompt"], seed=j["seed"], temperature=j["temperature"],
                     num_predict=j["num_predict"], base=base)
        except Exception as exc:  # noqa: BLE001
            r = {"error": f"{exc.__class__.__name__}: {exc}", "response": ""}
        with lock:
            results.append((idx, r))

    threads = [threading.Thread(target=worker, args=(i, j)) for i, j in enumerate(jobs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def _first_divergence(a: str, b: str) -> int:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return min(len(a), len(b))


def summarise(label: str, texts: list[str]) -> tuple[int, list[str]]:
    clusters: dict[str, list[str]] = {}
    for t in texts:
        clusters.setdefault(hashlib.sha256(t.encode()).hexdigest()[:16], []).append(t)
    print(f"\n== {label}: n={len(texts)} 簇数={len(clusters)}")
    for h, group in clusters.items():
        print(f"   [{h}] x{len(group)} len={len(group[0])} :: {group[0][:70]!r}")
    if len(clusters) > 1:
        groups = list(clusters.values())
        off = _first_divergence(groups[0][0], groups[1][0])
        print(f"   ⚠️ 首处分歧 offset={off}: A={groups[0][0][max(0,off-20):off+20]!r} | "
              f"B={groups[1][0][max(0,off-20):off+20]!r}")
    return len(clusters), list(clusters)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:1.5b")
    ap.add_argument("--base", default="http://127.0.0.1:11434")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--decoys", type=int, default=3)
    ap.add_argument("--num-predict", type=int, default=48)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--modes", default="sequential,concurrent,mixed")
    ap.add_argument("--json-out", default="")
    a = ap.parse_args(argv)
    modes = [m.strip() for m in a.modes.split(",") if m.strip()]

    print(f"model={a.model} base={a.base} runs={a.runs} seed={a.seed} temp={a.temperature}")
    print(f"prompt_sha={hashlib.sha256(a.prompt.encode()).hexdigest()[:16]}")
    report = {"model": a.model, "seed": a.seed, "temperature": a.temperature,
              "num_predict": a.num_predict, "runs": a.runs, "modes": {}}
    clusters_total = 0
    order = ["sequential", "concurrent", "mixed"]
    modes = [m for m in order if m in modes] or modes

    for mode in modes:
        texts: list[str] = []
        t0 = time.perf_counter()
        if mode == "sequential":
            for _ in range(a.runs):
                texts.append(call(a.model, a.prompt, seed=a.seed, temperature=a.temperature,
                                  num_predict=a.num_predict, base=a.base).get("response", ""))
        elif mode == "concurrent":
            res: list = []
            lock = threading.Lock()
            jobs = [{"model": a.model, "prompt": a.prompt, "seed": a.seed,
                     "temperature": a.temperature, "num_predict": a.num_predict}
                    for _ in range(a.runs)]
            _run_parallel(jobs, a.base, res, lock)
            texts = [r.get("response", "") for _, r in sorted(res, key=lambda p: p[0])]
        elif mode == "mixed":
            # 每轮 = 1 个目标请求 + decoys 个干扰请求，跑 runs 轮；只收目标文本。
            # （旧实现每模式只发一次，--runs 对它无效，n 恒为 2；已修）
            texts = []
            for rep in range(a.runs):
                res: list = []
                lock = threading.Lock()
                jobs = [{"model": a.model, "prompt": a.prompt, "seed": a.seed,
                         "temperature": a.temperature, "num_predict": a.num_predict}]
                for i in range(a.decoys):
                    # 干扰请求：不同 prompt、不同长度，制造异质 batch
                    jobs.append({"model": a.model,
                                 "prompt": f"Write one sentence about topic #{i}: " + ("filler " * (40 + 17 * i)),
                                 "seed": a.seed + i, "temperature": a.temperature,
                                 "num_predict": a.num_predict})
                _run_parallel(jobs, a.base, res, lock)
                ordered = [r for _, r in sorted(res, key=lambda p: p[0])]
                texts.append(ordered[0].get("response", ""))  # 目标请求（按 job 序号取，非完成顺序）
        else:
            print(f"skip unknown mode {mode}")
            continue

        n_clusters, hs = summarise(mode, texts)
        clusters_total += max(0, n_clusters - 1)
        report["modes"][mode] = {
            "clusters": n_clusters,
            "wall_s": round(time.perf_counter() - t0, 2),
            "hashes": hs,
            "texts": texts,
        }

    print(f"\nRESULT: {'FAIL' if clusters_total else 'OK'} — 非确定簇 {clusters_total} 个")
    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"saved {a.json_out}")
    return 3 if clusters_total else 0


if __name__ == "__main__":
    raise SystemExit(main())
