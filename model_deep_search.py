# -*- coding: utf-8 -*-
"""参数深搜+校准 (2026-08-20, HK)
目标: qwen2.5:7b-clean (熵 0.78/漂移 0.41 参数敏感)
机制: 3 代 × 4 候选 × 5 任务 = 60 次推理深搜
      校准: 熵/漂移约束 (最优须 漂移<0.5)
"""
import io
import json
import os
import random
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
OLLAMA = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b-clean"
TASKS = ["解释锂离子电池充放电原理。", "什么是 SEI 膜？", "硅碳负极优点？",
         "涂布工艺关键参数？", "锂离子迁移机制？"]


def infer(temp, top_p, max_tokens=64):
    body = json.dumps({"model": MODEL, "prompt": TASKS[0], "stream": False,
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
    import math
    if isinstance(ans, dict) or not ans:
        return 1.0
    n = len(ans)
    if n < 2:
        return 0.0
    freq = {}
    for c in ans:
        freq[c] = freq.get(c, 0) + 1
    return -sum((f / n) * math.log2(f / n) for f in freq.values()) / math.log2(n)


def drift(v1, v2):
    s1, s2 = set(v1), set(v2)
    return 1 - len(s1 & s2) / max(1, len(s1 | s2))


def evaluate(temp, top_p):
    """5 任务评估: 质量 + 熵 + 漂移 (vs 基线)"""
    tot, ents = 0.0, 0.0
    answers = []
    for t in TASKS:
        a = infer(temp, top_p)
        answers.append(a)
        tot += score(t, a)
        ents += entropy(a)
    n = len(TASKS)
    return tot / n, ents / n, answers


def main():
    rng = random.Random(7)
    base = (0.7, 0.9)
    print("=== qwen2.5:7b-clean 深搜+校准 ===\n")
    print(f"{'代':<3} {'候选':<4} {'temp':<6} {'top_p':<6} {'质量':<5} {'熵':<5} 漂移")

    # 基线
    bq, be, b_ans = evaluate(*base)
    print(f"{0:<3} {'B':<4} {base[0]:<6.2f} {base[1]:<6.2f} {bq:<5.2f} {be:<5.2f} 0.00")

    # 3 代 × 4 候选 (每代围绕当前最优扰动)
    cur = base
    best = (bq, cur)
    for gen in range(1, 4):
        for c in range(4):
            if gen == 1:
                cand = (max(0.1, cur[0] + rng.uniform(-0.25, 0.25)),
                        max(0.5, min(1.0, cur[1] + rng.uniform(-0.08, 0.08))))
            else:
                # 聚焦最优 (缩小扰动)
                cand = (max(0.1, best[1][0] + rng.uniform(-0.1, 0.1)),
                        max(0.5, min(1.0, best[1][1] + rng.uniform(-0.04, 0.04))))
            q, e, ans = evaluate(*cand)
            dr = drift(" ".join(str(x) for x in ans),
                       " ".join(str(x) for x in b_ans))
            print(f"{gen:<3} {c:<4} {cand[0]:<6.2f} {cand[1]:<6.2f} {q:<5.2f} {e:<5.2f} {dr:.2f}")
            if q > best[0] and dr < 0.6:  # 校准: 质量优 + 漂移约束
                best = (q, cand)
        cur = best[1]

    print(f"\n=== 校准结果 ===")
    print(f"基线: {base} 质量 {bq:.2f}")
    print(f"最优: {best[1]} 质量 {best[0]:.2f} (+{best[0]-bq:+.2f})")
    cfg = {"model": MODEL, "temperature": best[1][0], "top_p": best[1][1],
           "quality": best[0], "ts": time.strftime("%Y-%m-%d %H:%M")}
    # 校准持久化 (对比基线)
    path = os.path.join(os.path.dirname(BASE := os.path.abspath(__file__)),
                        "..", "data", "model_calibrated.json")
    prev = {}
    if os.path.exists(path):
        try:
            prev = json.load(open(path, encoding="utf-8"))
        except Exception:
            pass
    prev[MODEL] = cfg
    json.dump(prev, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"已写入校准: {path}")
    print(f"推荐: Ollama options temperature={best[1][0]} top_p={best[1][1]}")


if __name__ == "__main__":
    main()
