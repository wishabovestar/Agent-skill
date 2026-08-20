# -*- coding: utf-8 -*-
"""迭代优化引擎批量注入 v1.0 (2026-08-20, HF2)
通用性: 任意 Ollama 模型 × 特化任务集
机制: 每模型 1 代 × 2 候选 × 3 任务 = 6 次推理
输出: 最优采样参数表 (周度对比基线)

用法: model_evo_batch.py [模型名...] (默认全部 6 模型)
"""
import io
import json
import os
import random
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(os.path.dirname(BASE), "data", "model_evo_batch.json")
OLLAMA = "http://localhost:11434/api/generate"

# 6 模型 × 特化任务 (每模型能力域)
PROFILES = {
    "qwen2.5:7b-clean": ["解释锂离子电池充放电原理。", "什么是 SEI 膜？", "硅碳负极优点？"],
    "qwen2.5:7b": ["简述补锂工艺。", "涂布关键参数？", "石墨负极原理？"],
    "qwen2.5vl:3b": ["描述图像: 一只猫在桌子上", "OCR: 提取图中文字", "识别图中物体位置"],
    "ui-tars-1.5-7b:latest": ["如何点击登录按钮？", "界面元素分析步骤", "表单填写操作顺序"],
    "qwen2.5:0.5b": ["1+1=?", "水的沸点?", "CO2 是什么?"],
}

# 嵌入模型 (无生成, 排除)
EMBED_ONLY = {"bge-m3:latest"}


def infer(model, prompt, temp, top_p, max_tokens=64):
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "max_tokens": max_tokens, "temperature": temp,
                       "top_p": top_p}).encode()
    req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["response"].strip()
    except Exception as e:
        return {"error": str(e)}


def score(prompt, ans):
    if isinstance(ans, dict):
        return 0.0
    s = 0.0
    if 10 <= len(ans) <= 250:
        s += 0.5
    core = [w for w in prompt.split() if len(w) > 1][:2]
    if any(c[:2] in ans for c in core):
        s += 0.5
    return s


def entropy(ans):
    """响应熵 (香农): 低熵=确定/机械, 高熵=多样/不确定
    J-Space 熵分数 (HI 吸收): 评估响应不确定性"""
    if isinstance(ans, dict) or not ans:
        return 1.0
    n = len(ans)
    if n < 2:
        return 0.0
    freq = {}
    for c in ans:
        freq[c] = freq.get(c, 0) + 1
    import math
    return -sum((f / n) * math.log2(f / n) for f in freq.values()) / math.log2(n)


def drift(v1, v2):
    """版本漂移: 两版本文本差异率 (0-1)
    J-Space 漂移分数 (HI 吸收): 迭代间稳定性"""
    if not v1 or not v2:
        return 0.0
    s1, s2 = set(v1), set(v2)
    return 1 - len(s1 & s2) / max(1, len(s1 | s2))


def evolve_model(model, tasks):
    """单模型 1 代搜索: 默认 vs 2 候选 (含熵/漂移评估)"""
    rng = random.Random(42)
    base = (0.7, 0.9)
    candidates = [(base[0] + rng.uniform(-0.3, 0.3),
                   base[1] + rng.uniform(-0.1, 0.1)) for _ in range(2)]
    results = {}
    ans_cache = {}
    for cfg in [base] + candidates:
        tot = 0.0
        ents = 0.0
        for t in tasks[:3]:
            a = infer(model, t, cfg[0], cfg[1])
            ans_cache.setdefault(str(cfg), []).append(a)
            tot += score(t, a)
            ents += entropy(a)
        n = len(tasks[:3])
        results[str(cfg)] = tot / n
        results[str(cfg) + "_ent"] = ents / n
    best = max(results, key=lambda k: results[k] if not k.endswith("_ent") else -1)
    # 漂移: 最优配置 vs 基线 (同任务)
    drift_score = drift(
        " ".join(str(x) for x in ans_cache.get(best, [])),
        " ".join(str(x) for x in ans_cache.get(str(base), [])))
    return best, results[best], results[str(base)], results[best + "_ent"], drift_score


def load_state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def main():
    args = sys.argv[1:]
    models = [m for m in (args if args else list(PROFILES.keys())) if m not in EMBED_ONLY]
    st = load_state()
    print("=== 迭代优化引擎批量注入 v2 (熵/漂移/签名评估) ===\n")
    print(f"{'模型':<22} {'基线':<5} {'最优':<5} {'熵':<5} {'漂移':<5} 改善")
    for m in models:
        if m not in PROFILES:
            continue
        try:
            best, b_score, base_score, ent, dr = evolve_model(m, PROFILES[m])
        except Exception as e:
            print(f"{m:<22} ❌ {e}")
            continue
        delta = b_score - base_score
        print(f"{m:<22} {base_score:<5.2f} {b_score:<5.2f} {ent:<5.2f} {dr:<5.2f} "
              f"{'+' if delta > 0.02 else '·'}{delta:+.2f}")
        st[m] = {"best_cfg": best, "best_score": b_score,
                 "base_score": base_score, "entropy": ent, "drift": dr,
                 "ts": time.strftime("%Y-%m-%d %H:%M")}
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n结果已存: {STATE}")
    print(f"通用性: 任意 Ollama 模型 + 特化任务集 (PROFILES 可扩展)")


if __name__ == "__main__":
    main()
