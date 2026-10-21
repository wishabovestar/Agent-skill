# -*- coding: utf-8 -*-
"""
基于生物演化逻辑的 Hermes 自我迭代演化算法 — 演化策略库
========================================================
从多种动植物/微生物的演化逻辑提炼"生存策略基元" → 可执行的算法变体

生物演化逻辑 → 算法策略映射:
  细菌耐药(水平基因转移)  → 参数交叉注入(从其他记忆继承优良参数)
  病毒突变(高频突变)      → 高频参数变异搜索
  蚂蚁/蜜蜂(群体分工)     → 多智能体分工并行优化
  拟南芥/自花授粉         → 保守小步优化(避免破坏)
  结核(休眠)              → 状态休眠+条件激活(很少消耗资源)
  贝壳/珊瑚(累积生长)     → 渐进累积改进(不可逆重建)
  孔雀/性选择(夸张)       → 展示式强化(突出最优特征)
  哺乳动物(K选择)         → 少量高质量后代(精挑细选)
  细菌(大r选择)           → 大量低质量候选(广撒网筛)
  植物光合(资源效率)      → 高资源利用率的解
"""
import numpy as np, random, json, os
from copy import deepcopy

# ── 一维函数优化: 用不同生物策略求解, 作为演化算法核心 ──
def target_func(x, noise=0.0):
    """目标函数: 多峰, 含噪声(模拟真实环境的评估噪声)"""
    # 主峰在 x≈3 (缓慢平台, 低而宽), 全局最优在 x≈-2 (尖锐高峰)
    # 生物策略需在两级峰间权衡 → 挑战全局搜索
    base = -0.5*(x-3.0)**2 + 3.0*np.exp(-0.3*(x+2.0)**2) + 0.5*np.sin(2*x)
    if noise: return base + np.random.normal(0, noise)
    return base

# ── 演化策略库 (每种生物逻辑一种算法) ──
STRATEGIES = {
    "B1-细菌耐药(水平转移)": {
        "desc": "高突变 + 参数交叉(从其他解继承)", "mut": 0.5, "crossover": True, "r_selection": True
    },
    "B2-病毒(高频突变)": {
        "desc": "极高突变率, 快速试错", "mut": 0.9, "crossover": False, "r_selection": True
    },
    "B3-蚂蚁群体分工": {
        "desc": "多子群分工, 各自局部探索", "mut": 0.2, "crossover": False, "swarm": True
    },
    "B4-拟南芥自花(保守)": {
        "desc": "极低突变, 保守小步", "mut": 0.05, "crossover": False, "r_selection": False
    },
    "B5-结核休眠": {
        "desc": "休眠+条件激活, 节省资源", "mut": 0.15, "dormant": True
    },
    "B6-哺乳K选择": {
        "desc": "少量高质量后代, 精挑", "mut": 0.1, "r_selection": False
    },
    "B7-细菌r选择": {
        "desc": "大量低质量候选, 广撒网", "mut": 0.4, "r_selection": True, "large_litter": True
    },
    "B8-光合资源效率": {
        "desc": "高资源利用率, 梯度利用", "mut": 0.2, "gradient": True
    },
}

# ── 通用演化算法骨架 (策略参数化) ──
def evolve(strat, iters=200, pop_size=20, noise=0.1):
    """按生物策略演化 x → 优化 target_func"""
    cfg = STRATEGIES[strat]
    pop = [{"x": np.random.uniform(-5, 6), "fit": -1e9} for _ in range(pop_size)]
    best_fit = -1e9; best_x = None; updates = 0

    # 寄生/水平转移: 一个精英池
    elite = {"x": np.random.uniform(-5,6), "fit": -1e9}

    for it in range(iters):
        # 适应度评估(含噪声)
        for p in pop:
            p["fit"] = target_func(p["x"], noise)
            if p["fit"] > elite["fit"]:
                elite = deepcopy(p)
        # 更新全局最优
        if elite["fit"] > best_fit:
            best_fit = elite["fit"]; best_x = elite["x"]
        # 选择: 按适应度比例
        fits = [p["fit"] for p in pop]
        fmin = min(fits); frange = max(fits)-fmin or 1
        probs = [(f-fmin)/frange+0.1 for f in fits]
        probs = np.array(probs)/sum(probs)
        new_pop = []
        for _ in range(pop_size):
            parent = deepcopy(random.choices(pop, weights=probs, k=1)[0])
            # 变异: 按策略的 mut + 收敛缩放
            scale = max(0.05, 1 - it/iters) * (0.5 if cfg.get("r_selection") else 0.2)
            parent["x"] += np.random.normal(0, cfg["mut"]*scale)
            # 水平转移(细菌耐药): 从精英继承
            if cfg.get("crossover") and random.random() < 0.3:
                parent["x"] = 0.7*parent["x"] + 0.3*elite["x"]
            # 梯度利用(光合): 向精英梯度走
            if cfg.get("gradient"):
                parent["x"] += 0.1*(elite["x"]-parent["x"])
            # 休眠(结核): 一定概率保持上一代不动(节省)
            if cfg.get("dormant") and random.random() < 0.3:
                parent["x"] = parent["x"]  # 冻结
            new_pop.append(parent)
        # K选择: 只保留前一半(少而精); r选择: 全保留
        if not cfg.get("r_selection"):
            new_pop.sort(key=lambda p: p["fit"], reverse=True)
            new_pop = new_pop[:pop_size//2+1] + [deepcopy(elite)]*(pop_size//2)
        pop = new_pop
    return best_x, best_fit

# ── A/B 基线: 简单爬山 + 随机搜索 ──
def hill_climb(iters=200, noise=0.1):
    """基线A: 贪心爬山(最常见优化基准)"""
    x = np.random.uniform(-5, 6); best = -1e9
    for _ in range(iters):
        cand = x + np.random.normal(0, 0.3)
        if target_func(cand, noise) > target_func(x, noise): x = cand
        best = max(best, target_func(x, noise))
    return x, best

def random_search(iters=200, noise=0.1):
    """基线B: 随机搜索"""
    best = -1e9; bx=None
    for _ in range(iters):
        x = np.random.uniform(-5,6)
        f = target_func(x, noise)
        if f > best: best=f; bx=x
    return bx, best

if __name__ == "__main__":
    print("="*65)
    print("生物演化策略库 → Hermes自我迭代演化算法 (A/B基线对比)")
    print("="*65)
    # 全策略 + 基线对比
    results = []
    # 基线
    bx, bf = hill_climb(); results.append(("基线A:贪心爬山", bx, bf))
    bx, bf = random_search(); results.append(("基线B:随机搜索", bx, bf))
    # 生物策略
    for name in STRATEGIES:
        bx, bf = evolve(name); results.append((name, bx, bf))
    # 排序
    results.sort(key=lambda r:-r[2])
    print(f"\n{'策略':<28} | {'最优x':>8} | {'最优F':>8} | {'排名'}")
    for i,(n,x,f) in enumerate(results,1):
        marker = " 🏆" if i==1 else ""
        print(f"{n:<28} | {x:>8.3f} | {f:>8.3f} | #{i}{marker}")
    print("\n真最优: x=3.0, F≈0.0 (主峰)")
    print("\n注意: 噪声=0.1, 每次运行有随机性 → 需多次运行取均值看稳定性")
