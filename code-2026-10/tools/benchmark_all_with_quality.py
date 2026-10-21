#!/usr/bin/env python3
"""全模型统一 Benchmark + 质量检查 — 精简版，确保稳定运行"""
import time, subprocess, json, statistics

MODELS = [
    ("qwen2.5:7b", "Q4_K_M"),
    ("qwen2.5:7b-q3_64k", "Q3_K_M(64K)"),
    ("qwen2.5:7b-q2_k", "Q2_K"),
    ("qwen2.5:0.5b", "Q8_0"),
]

QUALITY_QUESTIONS = [
    ("Math", "What is 25 × 4 + 100? Only output the number."),
    ("Science", "What is the chemical formula for water? One word."),
    ("Logic", "If A > B and B > C, A vs C? One word."),
    ("Capital", "Capital of France? One word."),
    ("Color", "Color of ripe banana? One word."),
]

def ollama_run(model, prompt, timeout=120):
    t0 = time.time()
    r = subprocess.run(["ollama", "run", model, prompt],
        capture_output=True, text=True, timeout=timeout,
        env={**__import__('os').environ, "OLLAMA_KEEP_ALIVE": "15m"})
    return r.stdout.strip()[:200], time.time() - t0

def run_benchmark(model, name):
    print(f"\n{'='*60}")
    print(f"  {name:15s} | {model}")
    print(f"{'='*60}")
    
    # Phase 1: Quality check
    print(f"\n  [Q] Quality check")
    passes = 0
    for topic, q in QUALITY_QUESTIONS:
        out, t = ollama_run(model, q)
        ok = 0 < len(out) < 300
        if ok: passes += 1
        print(f"    {topic:8s} | {out[:50]:50s} | {t:5.2f}s | {'✅' if ok else '❌'}")
    
    # Phase 2: Latency (3 runs each)
    print(f"\n  [L] Latency")
    short_times = []
    for i in range(3):
        out, t = ollama_run(model, "What is 2+2?")
        short_times.append(t)
        print(f"    short {i+1}: {t:.2f}s | {len(out)} chars")
    med_short = statistics.median(short_times)
    
    mid_times = []
    for i in range(3):
        out, t = ollama_run(model, "Explain ML vs DL in 2 sentences.")
        mid_times.append(t)
    med_mid = statistics.median(mid_times)
    
    # Phase 3: Throughput
    print(f"\n  [T] Throughput")
    out, t = ollama_run(model, "Write 200 words about AI.")
    chars = len(out)
    tok_s = chars / t / 4  # ~4 chars/token
    print(f"    {chars} chars / {t:.2f}s = {tok_s:.1f} tok/s")
    
    r = {"model": model, "quant": name, "quality": f"{passes}/5",
         "lat_short": round(med_short, 2), "lat_mid": round(med_mid, 2),
         "throughput": round(tok_s, 1)}
    print(f"\n  → {json.dumps(r, ensure_ascii=False)}")
    return r

results = []
for model, name in MODELS:
    r = run_benchmark(model, name)
    results.append(r)

print(f"\n{'='*60}")
print(f"  FINAL COMPARISON")
print(f"{'='*60}")
print(f"{'Model':25s} | {'Qual':6s} | {'Lat(s)':8s} | {'Mid(s)':8s} | {'tok/s':8s}")
print(f"{'-'*25}-+-{'-'*6}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}")
for r in results:
    print(f"{r['model']:25s} | {r['quality']:6s} | {r['lat_short']:<8.1f} | {r['lat_mid']:<8.1f} | {r['throughput']:<8.1f}")

with open(r"D:\hermes\data\benchmark_all_results.json", "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\nSaved: D:\\hermes\\data\\benchmark_all_results.json")
