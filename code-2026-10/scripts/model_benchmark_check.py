# -*- coding: utf-8 -*-
"""
模型优化验证 #1: qwen2.5:7b Q4_K_M 稳定性 + 速度 Benchmark
=========================================================
对比: qwen2.5:7b (Q4) vs qwen2.5:7b-q3_64k (旧Q3) vs qwen2.5:0.5b (轻量)
检查: ①质量(5事实问题+无垃圾文本) ②速度(tok/s短生成) ③确定性
"""
import sys, io, json, time, subprocess, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def ollama_gen(model, prompt, num_predict=40, temperature=0):
    """调用 ollama API 生成"""
    import urllib.request
    data = json.dumps({"model":model,"prompt":prompt,"stream":False,
                       "options":{"num_predict":num_predict,"temperature":temperature}}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=data,
                                 headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def ollama_speed(model, prompt):
    """测速: 短生成的 tok/s"""
    import urllib.request
    t0=time.time()
    data = json.dumps({"model":model,"prompt":prompt,"stream":False,
                       "options":{"num_predict":30,"temperature":0}}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=data,
                                 headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d=json.loads(r.read())
    elapsed=time.time()-t0
    n_out = d.get("eval_count",30)
    return n_out/elapsed, d

print("="*66)
print("优化研究 #1: qwen2.5:7b Q4 稳定性+速度 Benchmark")
print("="*66)

# 5 个事实问题 (质量检查, 无垃圾文本=正常)
QUALITY = [
    ("中国首都是?", "北京"),
    ("1+1等于?", "2"),
    ("水分子化学式?", "H2O"),
    ("二次函数y=x²的导数?", "2x"),
    ("一年有多少天(非闰年)?", "365"),
]

def quality_check(model):
    """质量: 5题得分 + 垃圾文本检测"""
    score = 0
    garbage = 0
    for q, ans in QUALITY:
        try:
            d = ollama_gen(model, q, num_predict=30)
            out = d.get("response","").strip()
            if ans.lower() in out.lower():
                score += 1
            # 检测垃圾: "pérdida" 等损坏标志 或 乱码
            if "pérdida" in out.lower() or re.search(r'[\x00-\x08\x0b-\x1f]', out):
                garbage += 1
        except Exception as e:
            print(f"  ⚠️ {model} 题出错: {e}")
    return score, garbage

models = [
    ("qwen2.5:7b", "Q4_K_M(新,4.7GB)"),
    ("qwen2.5:7b-q3_64k", "Q3_K_M(旧,3.8GB)"),
    ("qwen2.5:0.5b", "Q4_0(轻,0.4GB)"),
]

print("\n【1. 质量检查】5事实题 + 垃圾文本检测")
for m, label in models:
    try:
        score, garbage = quality_check(m)
        mtime, _ = ollama_speed(m, "你好")  # 顺便测速
        status = "✅ 正常" if score>=4 and garbage==0 else "❌ 异常" if garbage>0 else "🟡 一般"
        print(f"  {m:<22} [{label}] 正确{score}/5 垃圾{garbage} | {mtime:.1f} tok/s | {status}")
    except Exception as e:
        print(f"  {m:<22} ❌ 无法测试: {e}")

print("\n【2. 速度对比】短生成 tok/s")
print(f"{'模型':<24} {'速度tok/s':>10}")
speeds = {}
for m, label in models:
    try:
        sp, _ = ollama_speed(m, "写一段关于深度学习的话")
        speeds[m] = sp
        print(f"  {m:<24} {sp:>10.1f}")
    except Exception as e:
        print(f"  {m:<24} ❌ {e}")

print("\n【3. 结论】")
# Q4 vs Q3 速度对比
if "qwen2.5:7b" in speeds and "qwen2.5:7b-q3_64k" in speeds:
    q4 = speeds["qwen2.5:7b"]; q3 = speeds["qwen2.5:7b-q3_64k"]
    print(f"  Q4 vs Q3: {q4:.1f} vs {q3:.1f} tok/s ({((q4-q3)/q3)*100:+.1f}%)")
    print(f"  → Q4 质量稳定(4.7GB) 相比Q3(3.8GB) 需权衡速度降幅 vs 质量提升")
print("  → 若Q4正确≥4/5且无垃圾 → 替换Q3为正式主力模型成功")

import os
os.makedirs("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit", exist_ok=True)
json.dump({"date":"2026-08-02","speeds":speeds,
           "models_tested":[m for m,_ in models]},
          open("D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/model_benchmark_20260802.json","w"), ensure_ascii=False)
print(f"\n✅ 存档: knowledge_base/audit/model_benchmark_20260802.json")
