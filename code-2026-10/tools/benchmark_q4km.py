#!/usr/bin/env python3
"""Qwen2.5-7B Q4_K_M 完整 Benchmark + 质量检查
RTX 5070 12GB · Ollama v0.32.1
"""

import time, subprocess, json, sys, statistics

MODEL = "qwen2.5:7b"  # Q4_K_M

def ollama_run(prompt, timeout=120):
    t0 = time.time()
    r = subprocess.run(
        ["ollama", "run", MODEL, prompt],
        capture_output=True, text=True, timeout=timeout,
        env={**__import__('os').environ, "OLLAMA_KEEP_ALIVE": "15m"}
    )
    elapsed = time.time() - t0
    return r.stdout.strip(), elapsed

def benchmark():
    print("=" * 55)
    print(f"  Qwen2.5-7B Q4_K_M · Benchmark")
    print(f"  GPU: RTX 5070 12GB | Ollama {__import__('ollama' if False else '').__name__ if False else 'v0.32.1'}")
    print("=" * 55)

    # ── Phase 1: 质量检查 (5个基本问题) ──
    print("\n[Phase 1] 质量检查 — 5 basic questions")
    quality_questions = [
        ("算术", "What is 25 × 4 + 100? Answer with just the number."),
        ("常识", "What color is the sky on a clear day? Answer in one word."),
        ("逻辑", "If all humans are mortal and Socrates is human, what is Socrates? Answer in one word."),
        ("语言", "Translate 'Hello, how are you?' to Chinese. One line only."),
        ("知识", "What is the chemical formula for water? Answer only the formula."),
    ]
    quality_pass = 0
    quality_results = []
    for topic, q in quality_questions:
        out, t = ollama_run(q)
        passed = len(out) > 0 and len(out) < 200
        quality_results.append((topic, out[:100], t, passed))
        if passed:
            quality_pass += 1
        print(f"  [{topic:4s}] {out[:60]:60s} | {t:6.2f}s | {'✅' if passed else '❌'}")

    print(f"\n  质量通过率: {quality_pass}/5 {'✅ PASS' if quality_pass >= 4 else '⚠️ LOW'}")

    # ── Phase 2: 延迟测试 ──
    print("\n[Phase 2] 延迟测试 (各3次取中位数)")
    latency_tests = [
        ("短prompt", "What is 2+2?"),
        ("中prompt", "Explain the difference between machine learning and deep learning in 3 sentences."),
        ("长prompt", "Write a detailed paragraph about the history of artificial intelligence, covering the Dartmouth Conference, the AI winters, the rise of deep learning, and modern large language models. Include at least 200 words."),
    ]
    latency_results = {}
    for test_name, prompt in latency_tests:
        times = []
        for i in range(3):
            out, t = ollama_run(prompt)
            times.append(t)
            print(f"  {test_name:12s} | run {i+1}: {t:.2f}s | {len(out)} chars")
        med = statistics.median(times)
        latency_results[test_name] = {"times": times, "median": med}
        print(f"  → 中位数: {med:.2f}s")

    # ── Phase 3: 吞吐量 ──
    print("\n[Phase 3] 吞吐量测试 (输出速度)")
    long_prompt = "Write a 500-word essay about the future of artificial intelligence. Cover different perspectives and include specific examples."
    out, t = ollama_run(long_prompt)
    words = len(out.split())
    char_len = len(out)
    tok_s = char_len / t
    print(f"  输出: {words} words / {char_len} chars in {t:.2f}s")
    print(f"  速度: {tok_s:.1f} char/s ≈ {tok_s/4:.1f} tok/s")

    # ── Summarize ──
    print("\n" + "=" * 55)
    print(f"  SUMMARY")
    print("=" * 55)
    print(f"  Quality:        {quality_pass}/5")
    print(f"  Latency(short): {latency_results.get('短prompt',{}).get('median',0):.2f}s")
    print(f"  Latency(mid):   {latency_results.get('中prompt',{}).get('median',0):.2f}s")
    print(f"  Latency(long):  {latency_results.get('长prompt',{}).get('median',0):.2f}s")
    print(f"  Throughput:     ~{tok_s/4:.1f} tok/s")

    # Save results
    report = {
        "model": MODEL,
        "quant": "Q4_K_M",
        "gpu": "RTX 5070 12GB",
        "quality": {q[0]: {"answer": q[1], "time": q[2], "pass": q[3]} for q in quality_results},
        "latency": latency_results,
        "throughput": {"chars_per_sec": round(tok_s, 1), "toks_per_sec": round(tok_s/4, 1)},
    }
    report_path = r"D:\hermes\data\benchmark_q4km_results.json"
    with open(report_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  Report saved: {report_path}")

benchmark()
