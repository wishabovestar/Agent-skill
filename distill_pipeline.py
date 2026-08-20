# -*- coding: utf-8 -*-
"""蒸馏数据管道 (2026-08-20, HP-P1)
教师 = DeepSeek API (响应蒸馏 — API 无 logits)
学生 = qwen2.5:7b (本地 LoRA SFT)
数据: 任务 → 教师响应 (soft target 文本)
"""
import json
import os
import sys
import time
import urllib.request

sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(BASE), "data", "distill_data.jsonl")

# 任务集: 锂电专业 + 通用推理 (教师蒸馏目标)
TASKS = [
    "解释锂离子电池充放电原理。",
    "什么是 SEI 膜？形成条件和作用？",
    "硅碳负极的优点和挑战？",
    "涂布工艺关键参数有哪些？",
    "锂离子在电解质中的迁移机制？",
    "压延锂带补锂的原理和优势？",
    "石墨负极首次库仑效率影响因素？",
    "电解液添加剂的作用机制？",
    "电池热失控的触发条件？",
    "负极材料粒径对性能的影响？",
    "1+1=？请直接回答。",
    "水的沸点是多少？",
    "地球绕太阳一周需要多久？",
    "解释牛顿第三定律。",
    "什么是质数？举例说明。",
]


def load_key(name):
    env = os.path.join(os.path.dirname(BASE), ".env")
    for line in open(env, encoding="utf-8"):
        if line.startswith(name + "="):
            return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def teacher_call(prompt):
    """DeepSeek 教师 API (V4 Pro)"""
    key = load_key("DEEPSEEK_API_KEY")
    if not key:
        return None
    body = json.dumps({
        "model": "deepseek-v4-pro",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300,
        "reasoning_budget": 100,
        "temperature": 0.3,
    }).encode()
    req = urllib.request.Request("https://api.deepseek.com/chat/completions",
                                 body, {"Content-Type": "application/json",
                                        "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read())
        return d["choices"][0]["message"]["content"].strip()


def main():
    print("=== 蒸馏数据管道 (DeepSeek 教师) ===")
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    out = open(DATA, "w", encoding="utf-8")
    n_ok = 0
    for i, task in enumerate(TASKS[:n]):
        ans = teacher_call(task)
        if ans:
            rec = {"task": task, "teacher": ans,
                   "ts": time.strftime("%Y-%m-%d %H:%M")}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            n_ok += 1
            print(f"  [{i+1}/{n}] ✅ {task[:20]}... ({len(ans)}字)")
        else:
            print(f"  [{i+1}/{n}] ❌ {task[:20]}... (无响应)")
        time.sleep(0.5)
    out.close()
    print(f"\n完成: {n_ok}/{n} 条 → {DATA}")


if __name__ == "__main__":
    main()
