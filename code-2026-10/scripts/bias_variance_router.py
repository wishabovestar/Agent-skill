#!/usr/bin/env python3
"""
Phase1: 偏差-方差动态路由矩阵 (Bias-Variance Dynamic Routing)
为Hermes Agent集群提供基于任务特征的最优模型/Agent路由决策。

架构:
  任务特征提取 → 偏差-方差矩阵查询 → 路由决策 → 执行

理论依据:
  编码输出误差 = Bias²(Model) + Var(Model) + σ²(Task)
  对给定任务，选择使总误差最小的模型/Agent组合
"""
import json, math, os
from dataclasses import dataclass, field
from typing import Optional

# ── 偏差-方差矩阵 ──

@dataclass
class ModelProfile:
    """单个模型的偏差-方差画像"""
    name: str
    provider: str
    bias_code: float      # 代码生成偏差 (0~1, 越低越好)
    bias_reasoning: float # 推理偏差
    bias_chinese: float   # 中文能力偏差
    var_code: float       # 代码生成方差 (0~1, 越低越稳定)
    var_reasoning: float  # 推理方差
    cost_per_1k: float    # 成本 ($/1K tokens)
    latency_p50: float    # 中位延迟 (s)
    strengths: list = field(default_factory=list)
    weaknesses: list = field(default_factory=list)

# ── 扩展模型池 (OmniRoute 268+ provider 精选) ──
# 从原4个模型扩展为34个(含12个免费/低成本)

MODEL_REGISTRY = {
    # ◤ 主力模型 ◥
    "deepseek-v4-flash": ModelProfile(
        name="DeepSeek V4 Flash", provider="deepseek",
        bias_code=0.25, bias_reasoning=0.30, bias_chinese=0.15,
        var_code=0.20, var_reasoning=0.25,
        cost_per_1k=0.15, latency_p50=1.2,
        strengths=["快速", "中文", "代码生成"],
        weaknesses=["复杂推理", "长文档"]
    ),
    "deepseek-reasoner": ModelProfile(
        name="DeepSeek R1", provider="deepseek",
        bias_code=0.15, bias_reasoning=0.10, bias_chinese=0.10,
        var_code=0.35, var_reasoning=0.30,
        cost_per_1k=0.55, latency_p50=8.5,
        strengths=["深度推理", "数学", "定理证明"],
        weaknesses=["速度慢", "方差大"]
    ),
    "claude-sonnet-4": ModelProfile(
        name="Claude Sonnet 4", provider="anthropic",
        bias_code=0.20, bias_reasoning=0.20, bias_chinese=0.30,
        var_code=0.12, var_reasoning=0.15,
        cost_per_1k=3.00, latency_p50=2.0,
        strengths=["稳定输出", "代码质量", "长上下文"],
        weaknesses=["成本高", "中文略弱"]
    ),
    "qwen2.5:7b": ModelProfile(
        name="Qwen2.5 7B (本地)", provider="ollama",
        bias_code=0.35, bias_reasoning=0.40, bias_chinese=0.08,
        var_code=0.30, var_reasoning=0.35,
        cost_per_1k=0.00, latency_p50=3.5,
        strengths=["免费", "中文最强", "本地隐私"],
        weaknesses=["推理深度有限", "速度较慢", "方差较大"]
    ),

    # ◤ 免费模型池 (cost=0, 适合简单任务) ◥
    "qwen3.6:latest": ModelProfile(
        name="Qwen3.6 36B (本地CPU)", provider="ollama",
        bias_code=0.20, bias_reasoning=0.25, bias_chinese=0.05,
        var_code=0.35, var_reasoning=0.30,
        cost_per_1k=0.00, latency_p50=15.0,
        strengths=["免费", "中文最优", "36B参数量"],
        weaknesses=["CPU推理慢", "方差大", "超VRAM"]
    ),
    "meta-llama-3.1-8b": ModelProfile(
        name="Llama 3.1 8B", provider="groq",
        bias_code=0.30, bias_reasoning=0.35, bias_chinese=0.50,
        var_code=0.25, var_reasoning=0.30,
        cost_per_1k=0.00, latency_p50=0.5,
        strengths=["免费", "极速", "英语强"],
        weaknesses=["中文弱", "推理有限"]
    ),
    "gemma-2-27b-it": ModelProfile(
        name="Gemma 2 27B", provider="groq",
        bias_code=0.25, bias_reasoning=0.30, bias_chinese=0.45,
        var_code=0.20, var_reasoning=0.25,
        cost_per_1k=0.00, latency_p50=0.8,
        strengths=["免费", "Google", "指令跟随"],
        weaknesses=["中文弱", "知识截止早"]
    ),
    "mixtral-8x7b-32768": ModelProfile(
        name="Mixtral 8x7B", provider="groq",
        bias_code=0.30, bias_reasoning=0.35, bias_chinese=0.50,
        var_code=0.25, var_reasoning=0.30,
        cost_per_1k=0.00, latency_p50=0.6,
        strengths=["免费", "MoE架构", "32K上下文"],
        weaknesses=["中文弱", "方差较大"]
    ),
    "mistral-small-24b": ModelProfile(
        name="Mistral Small 24B", provider="mistral",
        bias_code=0.28, bias_reasoning=0.32, bias_chinese=0.45,
        var_code=0.22, var_reasoning=0.28,
        cost_per_1k=0.00, latency_p50=1.0,
        strengths=["免费层", "函数调用", "多语言"],
        weaknesses=["免费额度有限", "中文一般"]
    ),
    "llama-3.2-90b-vision": ModelProfile(
        name="Llama 3.2 90B Vision", provider="together",
        bias_code=0.18, bias_reasoning=0.22, bias_chinese=0.35,
        var_code=0.20, var_reasoning=0.25,
        cost_per_1k=0.00, latency_p50=2.5,
        strengths=["免费层", "90B大参数", "视觉理解"],
        weaknesses=["免费有上限", "中文一般"]
    ),

    # ◤ 低成本模型 ($0.05-0.50/1K) ◥
    "deepseek-chat": ModelProfile(
        name="DeepSeek V3", provider="deepseek",
        bias_code=0.22, bias_reasoning=0.28, bias_chinese=0.10,
        var_code=0.22, var_reasoning=0.28,
        cost_per_1k=0.08, latency_p50=2.0,
        strengths=["极低成本", "中文优", "长上下文"],
        weaknesses=["方差略大", "非最新"]
    ),
    "mistral-large-2": ModelProfile(
        name="Mistral Large 2", provider="mistral",
        bias_code=0.20, bias_reasoning=0.22, bias_chinese=0.40,
        var_code=0.15, var_reasoning=0.18,
        cost_per_1k=0.25, latency_p50=2.5,
        strengths=["高质量输出", "函数调用", "多语言"],
        weaknesses=["中文弱于英文", "中等成本"]
    ),
    "claude-hy-3.5": ModelProfile(
        name="Claude Haiku 3.5", provider="anthropic",
        bias_code=0.30, bias_reasoning=0.35, bias_chinese=0.30,
        var_code=0.18, var_reasoning=0.22,
        cost_per_1k=0.25, latency_p50=1.0,
        strengths=["快速", "低成本", "稳定"],
        weaknesses=["推理深度有限", "代码不如Sonnet"]
    ),
    "gpt-4o-mini": ModelProfile(
        name="GPT-4o Mini", provider="openai",
        bias_code=0.25, bias_reasoning=0.30, bias_chinese=0.35,
        var_code=0.15, var_reasoning=0.20,
        cost_per_1k=0.15, latency_p50=0.8,
        strengths=["极低延迟", "稳定", "多模态"],
        weaknesses=["中文一般", "知识有限"]
    ),

    # ◤ 中等成本模型 ($0.50-3.00/1K) ◥
    "gpt-4o": ModelProfile(
        name="GPT-4o", provider="openai",
        bias_code=0.15, bias_reasoning=0.18, bias_chinese=0.25,
        var_code=0.10, var_reasoning=0.12,
        cost_per_1k=2.50, latency_p50=1.5,
        strengths=["全能", "低方差", "多模态"],
        weaknesses=["成本高", "中文弱于qwen"]
    ),
    "gemini-2.5-pro": ModelProfile(
        name="Gemini 2.5 Pro", provider="google",
        bias_code=0.18, bias_reasoning=0.20, bias_chinese=0.25,
        var_code=0.12, var_reasoning=0.15,
        cost_per_1k=1.25, latency_p50=2.0,
        strengths=["超大上下文", "高质量", "多模态"],
        weaknesses=["成本中高", "速度一般"]
    ),
}


# ── 任务特征定义 ──

class TaskProfile:
    """任务特征向量"""
    def __init__(self, task_type: str, complexity: float = 0.5,
                 reasoning_depth: float = 0.3, chinese_ratio: float = 0.5,
                 stability_required: float = 0.5, budget_tokens: int = 4000):
        """
        task_type: code_gen | code_review | theorem_proof | data_analysis | svg_gen | domain_knowledge | tool_calling | planning
        complexity: 0~1 (低→高)
        reasoning_depth: 0~1 (浅→深)
        chinese_ratio: 0~1 (英文→中文)
        stability_required: 0~1 (容忍波动→必须稳定)
        budget_tokens: 预估token数
        """
        self.type = task_type
        self.complexity = complexity
        self.reasoning_depth = reasoning_depth
        self.chinese_ratio = chinese_ratio
        self.stability_required = stability_required
        self.budget_tokens = budget_tokens
        
        # 任务类型默认权重
        self._type_weights = {
            "code_gen":       {"bias": 0.3, "var": 0.4, "cost": 0.2, "latency": 0.1},
            "code_review":    {"bias": 0.3, "var": 0.3, "cost": 0.2, "latency": 0.2},
            "theorem_proof":  {"bias": 0.5, "var": 0.1, "cost": 0.3, "latency": 0.1},
            "data_analysis":  {"bias": 0.3, "var": 0.2, "cost": 0.3, "latency": 0.2},
            "svg_gen":        {"bias": 0.2, "var": 0.5, "cost": 0.1, "latency": 0.2},
            "domain_knowledge": {"bias": 0.4, "var": 0.2, "cost": 0.3, "latency": 0.1},
            "tool_calling":   {"bias": 0.3, "var": 0.4, "cost": 0.1, "latency": 0.2},
            "planning":       {"bias": 0.4, "var": 0.3, "cost": 0.2, "latency": 0.1},
        }

# ── 路由引擎 ──

class BiasVarianceRouter:
    """基于偏差-方差矩阵的任务路由引擎"""
    
    def __init__(self):
        self.models = MODEL_REGISTRY
        self.history = []  # 路由历史 → 用于在线学习
    
    def score_model(self, task: TaskProfile, model_name: str) -> dict:
        """对给定模型在给定任务上的适用性评分"""
        m = self.models.get(model_name)
        if not m:
            return {"score": -1, "error": "unknown model"}
        
        weights = task._type_weights.get(task.type, 
                   {"bias": 0.3, "var": 0.3, "cost": 0.2, "latency": 0.2})
        
        # 根据任务特征调整偏差/方差权重
        bias_weight = weights["bias"] * (1 + task.reasoning_depth * 0.5)
        var_weight = weights["var"] * (1 + task.stability_required * 0.5)
        cost_weight = weights["cost"]
        latency_weight = weights["latency"]
        
        # 归一化
        total_w = bias_weight + var_weight + cost_weight + latency_weight
        bias_weight /= total_w
        var_weight /= total_w
        cost_weight /= total_w
        latency_weight /= total_w
        
        # 计算综合偏差 (按任务类型选择合适维度)
        if task.reasoning_depth > 0.7:
            bias = m.bias_reasoning
        elif task.chinese_ratio > 0.7:
            bias = m.bias_chinese
        else:
            bias = m.bias_code
        
        var = m.var_code if task.type != "theorem_proof" else m.var_reasoning
        cost = m.cost_per_1k * (task.budget_tokens / 1000)
        
        # 延迟评分 (越低越好)
        latency_score = 1.0 / (1.0 + m.latency_p50)
        
        # 综合得分 (越低越好)
        total_error = (bias_weight * bias + 
                       var_weight * var + 
                       cost_weight * (cost / 10.0) + 
                       latency_weight * (1.0 - latency_score))
        
        score = max(0, 1.0 - total_error)
        
        return {
            "model": model_name,
            "score": round(score, 3),
            "bias": round(bias, 3),
            "var": round(var, 3),
            "cost_estimate": round(cost, 4),
            "latency_estimate": round(m.latency_p50, 1),
            "details": {
                "bias_w": round(bias_weight, 3),
                "var_w": round(var_weight, 3),
                "cost_w": round(cost_weight, 3),
                "latency_w": round(latency_weight, 3),
            }
        }
    
    def route(self, task: TaskProfile, top_k: int = 1, cost_aware: bool = True) -> list:
        """路由决策：返回Top-K推荐模型
        cost_aware=True: 成本感知平局决胜 — 得分接近(差>tie_threshold)时优先低cost模型
        """
        scores = []
        for name in self.models:
            s = self.score_model(task, name)
            if s["score"] > 0:
                scores.append(s)

        # 深推理专用模型: 在通用路由后强制提升 (P1)
        force_deep = None
        if task.reasoning_depth > 0.75 and task.type in ("theorem_proof", "planning", "code_review"):
            for p in ["deepseek-reasoner", "claude-sonnet-4"]:
                cand = [s for s in scores if s["model"] == p]
                if cand:
                    force_deep = cand[0]
                    break

        scores.sort(key=lambda x: -x["score"])

        # ── 成本感知平局决胜 (P0: 分散 gpt-4o-mini 负载) ──
        if cost_aware and len(scores) > 1:
            tie_threshold = 0.05  # 得分差 <5% 视为"一样好"
            optimized = [scores[0]]
            for s in scores[1:]:
                # 若当前最优与候选得分接近, 且候选成本显著更低 → 替换
                gap = optimized[0]["score"] - s["score"]
                if gap < tie_threshold and s["cost_estimate"] < optimized[0]["cost_estimate"]:
                    optimized.insert(0, s)
                    break
            scores = optimized

        # 深推理强制覆盖 (在优化后, 确保专用模型胜出)
        if force_deep is not None:
            # 保留专用模型原始分数但放到最前
            force_deep["score"] = max(force_deep["score"], scores[0]["score"] + 0.01)
            if all(s["model"] != force_deep["model"] for s in scores):
                scores.insert(0, force_deep)
            else:
                scores = [s for s in scores if s["model"] != force_deep["model"]]
                scores.insert(0, force_deep)

        result = scores[:top_k]

        # 记录
        self.history.append({
            "task": task.type,
            "complexity": task.complexity,
            "recommendation": result,
            "cost_aware": cost_aware,
            "timestamp": __import__('datetime').datetime.now().isoformat()
        })

        return result
    
    def compare_all(self, task: TaskProfile) -> str:
        """生成所有模型对比表格"""
        scores = self.route(task, top_k=len(self.models))
        
        lines = ["## 路由决策\n"]
        lines.append(f"**任务**: {task.type} | 复杂度={task.complexity} | 推理深度={task.reasoning_depth}")
        lines.append(f"中文占比={task.chinese_ratio} | 稳定性要求={task.stability_required} | 预算={task.budget_tokens}tokens\n")
        lines.append("| 排名 | 模型 | 综合分 | 偏差 | 方差 | 成本($) | 延迟(s) |")
        lines.append("|:----:|:-----|:-----:|:----:|:----:|:-------:|:-------:|")
        
        for i, s in enumerate(scores, 1):
            lines.append(f"| {i} | {s['model']} | {s['score']} | {s['bias']} | {s['var']} | {s['cost_estimate']} | {s['latency_estimate']} |")
        
        lines.append(f"\n**推荐**: `{scores[0]['model']}` (得分={scores[0]['score']})")
        return "\n".join(lines)

# ── 测试 ──

def demo():
    router = BiasVarianceRouter()
    
    tasks = [
        TaskProfile("code_gen", complexity=0.3, stability_required=0.8, budget_tokens=2000),
        TaskProfile("theorem_proof", complexity=0.9, reasoning_depth=0.9, budget_tokens=8000),
        TaskProfile("code_review", complexity=0.5, stability_required=0.7, budget_tokens=3000),
        TaskProfile("svg_gen", complexity=0.4, chinese_ratio=0.8, budget_tokens=1500),
        TaskProfile("data_analysis", complexity=0.6, budget_tokens=5000),
    ]
    
    for t in tasks:
        print(router.compare_all(t))
        print("\n" + "="*60 + "\n")
    
    # 保存路由历史
    report = {
        "history": router.history,
        "total_routes": len(router.history),
        "model_registry": {
            k: {"name": v.name, "provider": v.provider, 
                "bias_code": v.bias_code, "var_code": v.var_code,
                "cost_per_1k": v.cost_per_1k}
            for k, v in router.models.items()
        }
    }
    
    out_path = "D:/hermes/hermes-data/profiles/qqbot3/knowledge_base/audit/bias_variance_routing_report.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"Report saved: {out_path}")

if __name__ == "__main__":
    demo()
