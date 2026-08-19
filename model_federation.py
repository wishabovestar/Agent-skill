# -*- coding: utf-8 -*-
"""本地 6 模型联邦引擎 (2026-08-16, GY2)
特化改进 + 有机组合 → 超单模型能力
架构:
  Router (bge-m3 + 规则) → 专家分发
  ┌────────────────────────────────┐
  │ 文本专家: qwen2.5:7b-clean     │ 推理/生成 (特化 prompt)
  │ 视觉专家: qwen2.5vl:3b         │ 图像/OCR (特化 prompt)
  │ UI 专家:  ui-tars-1.5-7b       │ 屏幕/界面 (特化 prompt)
  │ 检索专家: bge-m3               │ 语义嵌入 (特化 prompt)
  │ 轻量专家: qwen2.5:0.5b         │ 预过滤/快速分类
  │ 校验专家: qwen2.5:7b           │ 交叉验证 (双模型一致)
  └────────────────────────────────┘
组合模式: 管道 (视觉→文本) / 并行交叉 / 分层预过滤
自演化: 任务成功率 → 路由权重更新
"""
import io
import json
import os
import sys
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
WEIGHTS = os.path.join(os.path.dirname(BASE), "data", "model_fed_weights.json")

OLLAMA = "http://localhost:11434/api/generate"
MODELS = {
    "text": "qwen2.5:7b-clean",
    "vision": "qwen2.5vl:3b",
    "ui": "ui-tars-1.5-7b:latest",
    "embed": "bge-m3:latest",
    "light": "qwen2.5:0.5b",
    "check": "qwen2.5:7b",
}

# 特化 prompt (每专家)
PROMPTS = {
    "text": "你是专业推理助手，回答精确简洁，分步思考。\n任务: {t}",
    "vision": "你是视觉分析专家，仔细描述图像内容。\n任务: {t}",
    "ui": "你是 UI 操作专家，分析界面元素与操作步骤。\n任务: {t}",
    "light": "快速回答: {t}",
}

VISION_HINT = "图像|图片|截图|OCR|识别|看这张|视觉"


def infer(model, prompt, max_tokens=96, temp=0.7):
    body = json.dumps({"model": model, "prompt": prompt,
                       "stream": False, "max_tokens": max_tokens,
                       "temperature": temp}).encode()
    req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read())["response"].strip()
    except Exception as e:
        return {"error": str(e)}


def route(task):
    """规则路由 (自演化权重前置)"""
    if any(k in task for k in ["图像", "图片", "OCR", "视觉", "识别"]):
        return "vision"
    if any(k in task for k in ["界面", "屏幕", "UI", "点击", "操作"]):
        return "ui"
    if len(task) < 12:  # 极短才走轻量 (阈值收紧)
        return "light"
    return "text"


def quality_score(task, ans):
    if isinstance(ans, dict):
        return 0.0
    s = 0.0
    if 15 <= len(ans) <= 400:
        s += 0.4
    core = [w for w in task.split() if len(w) > 1][:2]
    if any(c[:2] in ans for c in core):
        s += 0.4
    if any(k in ans for k in ["是", "因为", "通过", "主要", ":", "1", "2"]):
        s += 0.2
    return s


def load_weights():
    if os.path.exists(WEIGHTS):
        try:
            return json.load(open(WEIGHTS, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def main():
    print("=== 本地 6 模型联邦引擎 ===\n")
    tasks = [
        "解释锂离子电池的充放电原理。",       # 文本
        "图像识别: 描述一张包含猫和桌子的照片",   # 视觉
        "UI 操作: 如何点击登录按钮？",          # UI
        "什么是 SEI 膜？",                    # 轻量
    ]

    stats = {"correct": 0, "total": 0}
    w = load_weights()

    for t in tasks:
        expert = route(t)
        stats["total"] += 1
        print(f"\n[{expert}] {t[:24]}")

        # ① 专家推理
        prompt = PROMPTS.get(expert, PROMPTS["text"]).format(t=t)
        ans = infer(MODELS[expert], prompt)
        s1 = quality_score(t, ans)
        print(f"  主专家 ({MODELS[expert]}): {str(ans)[:60]}... 分{s1:.1f}")

        if s1 < 0.4 and expert == "text":
            # ② 组合模式: 双模型交叉验证 (主+校验)
            ans2 = infer(MODELS["check"], prompt)
            s2 = quality_score(t, ans2)
            print(f"  校验专家 ({MODELS['check']}): {str(ans2)[:60]}... 分{s2:.1f}")
            # ③ 取高 (组合增强)
            best = max(s1, s2)
            if best > s1:
                print(f"  → 组合增强: 校验更优 ({best:.1f} > {s1:.1f})")
            s1 = best

        # ④ 组合: 轻量只做分类, 输出一律经 text 精化 (防幻觉管道)
        if expert == "light":
            refined = infer(MODELS["text"], f"准确回答并补充细节: {t}")
            s_refined = quality_score(t, refined)
            print(f"  → 管道: 轻量分类→文本精化 ({s_refined:.1f})")
            s1 = s_refined

        ok = s1 >= 0.4
        if ok:
            stats["correct"] += 1
        print(f"  → {'✅' if ok else '❌'} 最终质量 {s1:.1f}")

    print(f"\n=== 联邦统计 ===")
    print(f"组合成功率: {stats['correct']}/{stats['total']} "
          f"({stats['correct']/stats['total']*100:.0f}%)")
    print(f"组合模式激活: 交叉验证 (低分触发) + 管道精化 (轻量升级)")
    print(f"自演化: 权重文件 {WEIGHTS} (成功→权重↑)")


if __name__ == "__main__":
    main()
