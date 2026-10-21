#!/usr/bin/env python3
"""A/B测试: RDT自适应循环深度 vs 固定深度 — 验证借鉴效果
对照A: 固定max_iterations (现状)
实验B: 计算自适应 (收敛检测/预算/发散)

测试任务集: 5类典型Hermes任务, 各2个变体 (10任务)
指标: 完成率 / 耗时 / token消耗 / 质量评分
"""
import time, json, random

# ===== 模拟任务执行 (真实A/B由cron驱动, 此处为框架脚本) =====

TASKS = [
    ("direct_query", "查询当前天气", 15, 1),
    ("file_search", "在代码库找函数定义", 30, 2),
    ("research", "研究3篇论文", 55, 3),
    ("code_review", "审查一个PR", 60, 3),
    ("multi_agent", "跨域调研并出报告", 80, 4),
]

def simulate_execution(mode, task_name, complexity, base_iters):
    """模拟任务执行 - complexity归一化为1-5"""
    t0 = time.time()
    comp_norm = max(1, min(5, complexity // 20 + 1))  # 15→1, 30→2, 55→3, 60→4, 80→5
    if mode == "A_fixed":
        # 固定迭代: 按难度固定3轮
        iterations = 3
        success_prob = 0.75 + 0.05 * (5 - comp_norm)
        tokens = base_iters * 1000
    else:  # B_adaptive
        # 自适应: 简单任务少迭代, 复杂任务按复杂度/20轮
        iterations = max(1, min(5, complexity // 20))
        success_prob = 0.70 + 0.08 * (5 - comp_norm)
        tokens = iterations * 1000
    
    # 模拟执行
    time.sleep(0.05 * iterations)
    success = random.random() < success_prob
    elapsed = time.time() - t0
    quality = success * (0.8 + 0.04 * iterations)  # 更多迭代略高质量
    return {
        "task": task_name, "mode": mode,
        "iterations": iterations, "success": success,
        "elapsed_s": round(elapsed, 2), "tokens": tokens,
        "quality": round(quality, 2),
    }

def run_ab():
    results = []
    for task_name, desc, complexity, base_iters in TASKS:
        for mode in ["A_fixed", "B_adaptive"]:
            # 每个任务跑3次取平均
            runs = [simulate_execution(mode, task_name, complexity, base_iters) for _ in range(3)]
            avg = {
                "task": task_name, "mode": mode,
                "iterations": round(sum(r["iterations"] for r in runs)/3, 1),
                "success_rate": round(sum(1 for r in runs if r["success"])/3, 2),
                "elapsed_s": round(sum(r["elapsed_s"] for r in runs)/3, 2),
                "tokens": round(sum(r["tokens"] for r in runs)/3),
                "quality": round(sum(r["quality"] for r in runs)/3, 2),
            }
            results.append(avg)
    return results

def main():
    print("=" * 60)
    print("A/B测试: RDT自适应循环深度 (借鉴OpenMythos)")
    print("A组=固定迭代3轮 (现状) | B组=计算自适应 (借鉴)")
    print("=" * 60)
    
    results = run_ab()
    
    # 汇总
    print(f"\n{'任务':<14s} {'组':<10s} {'迭代':<6s} {'成功率':<8s} {'耗时s':<8s} {'token':<8s} {'质量':<6s}")
    print("-" * 60)
    for r in results:
        print(f"{r['task']:<14s} {r['mode']:<10s} {r['iterations']:<6.1f} {r['success_rate']:<8.2f} {r['elapsed_s']:<8.2f} {r['tokens']:<8.0f} {r['quality']:<6.2f}")
    
    # A/B对比
    a = [r for r in results if r["mode"] == "A_fixed"]
    b = [r for r in results if r["mode"] == "B_adaptive"]
    
    print("\n=== 汇总对比 ===")
    print(f"A组(固定): 平均耗时 {sum(r['elapsed_s'] for r in a)/len(a):.2f}s | 平均token {sum(r['tokens'] for r in a)/len(a):.0f} | 成功率 {sum(r['success_rate'] for r in a)/len(a):.2f}")
    print(f"B组(自适应): 平均耗时 {sum(r['elapsed_s'] for r in b)/len(b):.2f}s | 平均token {sum(r['tokens'] for r in b)/len(b):.0f} | 成功率 {sum(r['success_rate'] for r in b)/len(b):.2f}")
    
    # 计算收益
    time_save = (sum(r['elapsed_s'] for r in a) - sum(r['elapsed_s'] for r in b)) / len(a)
    token_save = (sum(r['tokens'] for r in a) - sum(r['tokens'] for r in b)) / len(a)
    print(f"\n📊 B组收益: 耗时 {time_save:.2f}s 减少 ({time_save/sum(r['elapsed_s'] for r in a)*len(a)*100:.0f}%) | token {token_save:.0f} 减少")
    
    # 保存
    with open(r'D:/hermes/data/ab_test_rdt_results.json', 'w', encoding='utf-8') as f:
        json.dump({"results": results, "timestamp": time.strftime("%Y-%m-%d %H:%M")}, f, ensure_ascii=False, indent=2)
    print("\n结果已保存: D:/hermes/data/ab_test_rdt_results.json")
    
    print("\n⚠️ 注: 此为模拟框架验证机制可用。真实A/B需在delegation层实现收敛检测后, 用实际任务跑1周。")

if __name__ == "__main__":
    main()
