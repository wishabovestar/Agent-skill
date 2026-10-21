# -*- coding: utf-8 -*-
"""算法/深度学习/神经网络 — 2026-08-30 巡天采集入库"""
import json, datetime

ENTRIES = [
    {"repo": "deepseek-ai/DeepSpec", "stars": 7051, "lang": "Python",
     "desc": "DeepSpec: full-stack codebase for training and evaluating speculative decoding algorithms",
     "tags": ["推测解码", "LLM推理加速", "DeepSeek", "算法训练"],
     "pushed": "2026-07-09", "score": 9,
     "note": "推测解码(speculative decoding)全栈实现，与Hermes本地推理优化(12GB显卡长上下文)直接相关，可参考其训练/评估管线"},
    {"repo": "Optima-CityU/LLM4AD_Next", "stars": 484, "lang": "Python",
     "desc": "Next-generation automatic algorithm design platform (alpha-evolve/open-loop/open-evolve)",
     "tags": ["自动算法设计", "LLM4AD", "演化算法", "alpha-evolve"],
     "pushed": "2026-08-29", "score": 8,
     "note": "LLM驱动的自动算法设计平台（DeepMind alpha-evolve开放版），数学组Agent可关注演化算法自动发现方向"},
    {"repo": "Xiangyue-Zhang/auto-deep-researcher-24x7", "stars": 1285, "lang": "Python",
     "desc": "Autonomous AI agent that runs deep learning experiments 24/7. Zero-cost monitoring",
     "tags": ["深度学习实验", "自动化Agent", "24x7"],
     "pushed": "2026-06+", "score": 7,
     "note": "睡眠期间自动跑深度学习实验的Agent，与Hermes sleep-research/自强化工作流理念一致"},
    {"repo": "mohi-devhub/antivibe", "stars": 1094, "lang": "Shell",
     "desc": "Learn what AI writes. Claude Code skill that turns AI-generated code into educational deep dives",
     "tags": ["Claude Code技能", "代码教学", "学习框架"],
     "pushed": "2026-06+", "score": 7,
     "note": "与Hermes已有antivibe技能同源，AI生成代码转教学材料"},
    {"repo": "maderix/ANE", "stars": 7254, "lang": "Objective-C",
     "desc": "Training neural networks on Apple Neural Engine via reverse-engineered private APIs",
     "tags": ["Apple Neural Engine", "边缘推理", "逆向工程"],
     "pushed": "2026-06+", "score": 6,
     "note": "Apple NPU逆向训练，边缘侧神经网络部署参考"},
    {"repo": "facebookresearch/ai4animationpy", "stars": 2080, "lang": "Python",
     "desc": "Python framework for AI-driven character animation using neural networks",
     "tags": ["角色动画", "神经网络", "Meta FAIR"],
     "pushed": "2026-06+", "score": 6,
     "note": "Meta FAIR神经网络动画框架"},
    {"repo": "vercel-labs/vgpu", "stars": 931, "lang": "TypeScript",
     "desc": "Modular cross-runtime WebGPU library for shaders, 3D scenes, GPU tensors, neural networks, math viz",
     "tags": ["WebGPU", "GPU张量", "神经网络"],
     "pushed": "2026-06+", "score": 6,
     "note": "跨运行时WebGPU神经网络库，浏览器端推理/可视化"},
    {"repo": "zarazhangrui/youtube-digest", "stars": 964, "lang": "JavaScript",
     "desc": "Turn YouTube videos into deep learning resources: transcripts, bilingual translation, AI overviews",
     "tags": ["YouTube转学习", "双语翻译", "学习资源"],
     "pushed": "2026-06+", "score": 5,
     "note": "视频转深度学习教材，youtube-content技能扩展参考"},
]

os = __import__("os")
base = "D:/hermes/data/agent_knowledge/算法"
os.makedirs(base, exist_ok=True)
path = f"{base}/scout_report_20260830.json"
with open(path, "w", encoding="utf-8") as f:
    json.dump({"date": "2026-08-30", "source": "GitHub Search API",
               "categories": ["algorithm", "deep-learning", "neural-network"],
               "entries": ENTRIES}, f, ensure_ascii=False, indent=1)
print(f"已入库: {path} ({len(ENTRIES)}条)")
# 汇总stats
print("总stars:", sum(e["stars"] for e in ENTRIES))
