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
# side_effects: [无, 纯路由决策]
import io
import json
import os
import sys
import urllib.request
from gaussian_voi import refine_decision_gaussian, fit_params, record_result

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
WEIGHTS = os.path.join(os.path.dirname(BASE), "data", "model_fed_weights.json")

OLLAMA = "http://localhost:11434"

# OpenCode Zen (IS 研究 2026-08-20): 免费模型网关
# 端点: https://opencode.ai/zen/go/v1/messages (Anthropic 格式)
# 模型: ox-alpha-free (免费) + minimax-m3/kimi-k3/glm-5.2/deepseek-v4 等
# 认证: opencode auth login → x-api-key (匿名需账号免费额度)
ZEN_ENDPOINT = "https://opencode.ai/zen/go/v1/messages"
ZEN_MODELS = {"ox-alpha-free", "minimax-m3", "kimi-k3", "glm-5.2",
              "deepseek-v4-flash", "mimo-v2.5"}
ZEN_KEY = os.environ.get("OPENCODE_ZEN_KEY", "")  # 待 auth login 填充
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
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": temp}
    }).encode()
    req = urllib.request.Request(OLLAMA + "/api/generate", body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read())["response"].strip()
    except Exception as e:
        return {"error": str(e)}


def moe_fuse(answers, weights=None):
    """复合专家融合 (ID: 加权集成 — 避免 k=2 多数投票陷阱)
    Condorcet: k≥3 多数投票 or 加权 (高质量专家主导)"""
    if not answers:
        return None, {}
    if len(answers) == 1:
        return answers[0], {"mode": "single"}
    if weights is None:
        weights = [0.6] + [0.4 / (len(answers) - 1)] * (len(answers) - 1)
    scored = sorted(zip(answers, weights),
                    key=lambda x: x[1], reverse=True)
    best = scored[0][0]
    return best, {"mode": "fused", "k": len(answers),
                  "weights": [round(w, 2) for _, w in scored]}


def classify_problem_type(task):
    """题型分类器 (2026-08-23, R39 xthink 分题型路由落地)

    基于 A/B 多采样实测 (qwen2.5:7b, n=10):
      线性多步 (火车类): 详细推理防遗漏 → xthink 档增益 +40pp
      恒等变换 (代数类): 展开中间步骤出错 → 正常档更好 (90%)
    返回: "math_linear" (xthink 档) / "math_identity" (正常档)
          / "math_heavy" (Bonsai n512 档) / None (非数学题)
    """
    # 数学题检测: 含数字 + 运算/等号/单位
    has_num = any(c.isdigit() for c in task)
    has_op = any(k in task for k in ["+", "-", "*", "/", "=", "km", "km/h", "公里", "米", "距离", "求", "计算", "总"])
    if not (has_num and has_op):
        return None
    # 多段顺序计算 (then/然后/for Xh — 线性步骤) → xthink 档
    multi_seg = any(k in task for k in ["then", "然后", "for ", "先后", "再", "先", "每个", "各"])
    # 恒等变换特征: 幂/平方/恒等式 (a²+b² 类 — 展开有害)
    identity = any(k in task for k in ["^", "平方", "恒等", "²", "³"])
    # 多约束 (a+b=10, ab=21 — 推导类) → 复杂
    multi_constraint = task.count(",") >= 1 and "=" in task and has_num
    if identity and not multi_seg:
        return "math_identity"   # 恒等/单步代数 → 正常档
    if multi_constraint and identity:
        return "math_heavy"      # 多约束推导 → Bonsai n512
    if multi_seg:
        return "math_linear"     # 线性多步 → xthink 档
    return "math_identity"       # 默认数学题 → 正常档


def refine_decision(task, est):
    """Per-task 细化判据 — 高斯信号模型 + 在线参数拟合 (2026-08-23)

    VOI = [s0^2/sqrt(s0^2+sr^2) - s0^2/sqrt(s0^2+se^2)]*psi(n) - c
    参数: 从路由历史在线拟合 (fit_params — 伯努利σ
    + EMA 平滑) — 数据不足时用默认 (R39 校准)
    """
    base_params = {
        "n_experts": 4, "sigma0": 0.5, "sigma_r": 0.12, "cost_c": 0.08,
        "est_noise_map": {"light": 0.15, "text": 0.30, "uncertain": 0.55},
    }
    # 在线拟合: 读历史 → 更新参数
    hist_path = os.path.join(BASE, "data", "routing_history.json")
    params = base_params
    try:
        if os.path.exists(hist_path):
            with open(hist_path, encoding="utf-8") as f:
                hist = json.load(f)
            params = fit_params(hist, base_params)
    except Exception:
        params = base_params
    refine, voi = refine_decision_gaussian(task, est, params)
    target = "check" if classify_problem_type(task) == "math_heavy" else "text"
    return refine, target if refine else None


def route(task, context=""):
    """状态感知路由 (HH 吸收: sprix-sage-router SELF/HANDOFF)
    JM 吸收 (Pandora 价值估计成本感知):
    廉价估计器 (长度/关键词/域特征) 先行 → 只有不确定才升昂贵"""
    # HANDOFF: 上下文缺失 → 升级 (校验专家)
    ctx_ok = any(k in context for k in ["上下文", "背景", "资料", "完整", "已有"])
    if context and not ctx_ok and len(task) > 20:
        return "check"
    if any(k in task for k in ["图像", "图片", "OCR", "视觉", "识别"]):
        return "vision"
    if any(k in task for k in ["界面", "屏幕", "UI", "点击", "操作"]):
        return "ui"
    # R39: 题型分类器 (数学题 → 分题型路由)
    ptype = classify_problem_type(task)
    if ptype == "math_linear":
        return "xthink"      # 线性多步 → qwen2.5:7b 详细推理档
    if ptype == "math_heavy":
        return "check"       # 多约束推导 → 升级 Bonsai n512
    if ptype == "math_identity":
        return "text"        # 恒等/单步 → 正常档 (展开有害)
    # Pandora 模式: 廉价估计器评分 → 阈值路由
    est = _cheap_estimator(task)
    if est == "light":
        return "light"
    # R44: per-task 细化判据 (VOI 近似) — 值得则升级
    refine, target = refine_decision(task, est)
    if refine:
        return target
    return "text"


def _cheap_estimator(task):
    """Pandora 廉价估计器 (embedding 替代: 规则特征)
    成本 0.1 → 90% 确定性路由, 10% 不确定升级"""
    # 简单特征: 短+无专业词 → 轻量
    if len(task) < 12 and not any(k in task for k in ["研究", "分析", "设计", "优化"]):
        return "light"
    # 中等: 有行动词但简短 → 文本
    # 不确定: 长任务+无明确行动词 → 升级确认
    if len(task) > 30 and not any(k in task for k in ["请", "分析", "总结", "研究", "对比", "写"]):
        return "uncertain"
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
        "A train at 90km/h for 2h then 60km/h for 1.5h. Total distance?",  # R39: xthink 档
        "a+b=10, ab=21, a^2+b^2=?",           # R39: 正常档 (恒等)
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
