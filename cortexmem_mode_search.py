# -*- coding: utf-8 -*-
"""CortexMem 模式感知检索 (2026-08-20, HR-P1 吸收)
RooFlow memory_bank_strategy 模式定制 → 任务类索引
机制: 任务分类 → 特化索引检索 (vs 统一全局)
"""
import json
import os
import time

BASE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.join(os.path.dirname(BASE), "knowledge_base")

# 任务类 → 知识库子目录 (特化索引)
MODE_INDEX = {
    "research": ["research"],
    "audit": ["audit"],
    "code": ["research", "audit"],
    "local_llm": ["research", "audit"],
    "vps": ["research", "audit"],
}


def classify(task):
    """任务分类 (规则)"""
    if any(k in task for k in ["研究", "论文", "项目", "分析"]):
        return "research"
    if any(k in task for k in ["测试", "验证", "A/B", "评估", "检查"]):
        return "audit"
    if any(k in task for k in ["代码", "脚本", "实现", "部署"]):
        return "code"
    if any(k in task for k in ["模型", "本地", "蒸馏", "微调"]):
        return "local_llm"
    if any(k in task for k in ["VPS", "站点", "推广", "SEO"]):
        return "vps"
    return "research"


def mode_search(task, query):
    """模式感知检索: 任务类 → 特化目录"""
    mode = classify(task)
    dirs = MODE_INDEX.get(mode, ["research"])
    hits = []
    for d in dirs:
        p = os.path.join(KB, d)
        if not os.path.isdir(p):
            continue
        for f in os.listdir(p)[:50]:
            if query in f or query.lower() in f.lower():
                hits.append(f"{d}/{f}")
    return mode, hits


def main():
    print("=== CortexMem 模式感知检索 (HR 吸收) ===\n")
    tests = [
        ("研究蒸馏基因", "distill"),
        ("A/B 测试吸收", "ab"),
        ("检查 VPS 推广", "vps"),
        ("本地模型迭代", "evo"),
    ]
    for task, q in tests:
        mode, hits = mode_search(task, q)
        print(f"  [{mode:<10}] {task:<12} → {len(hits)} 命中: {hits[:2]}")
    print("\n✅ 模式感知索引已落地 (MODE_INDEX 可扩展)")


if __name__ == "__main__":
    main()
