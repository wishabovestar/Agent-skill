# -*- coding: utf-8 -*-
"""基因演化逻辑应用: gene 推理引擎迭代 (2026-08-16, FW)
研究: 生物演化多机制 → 引擎迭代算子
① 随机变异 (mutation): 基因步骤扰动
② 自然选择 (selection): fitness 已有 (保留精英)
③ 遗传漂移 (genetic drift): 小群体随机波动 (非适应驱动, 防早收敛)
④ 缩减演化 (reductive evolution): 基因组精简 (删冗余步骤)
⑤ 中性突变 (neutral mutation): fitness 不变变异 (保持多样性)
⑥ 瓶颈效应 (bottleneck): 群体骤减后恢复 (弹性)
⑦ 基因流 (gene flow): 外部基因引入 (跨域吸收)
"""
import copy
import io
import json
import os
import random
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(os.path.dirname(BASE), "scripts", "evo_engine_state.json")

# 演化参数 (生物对标)
P_MUTATION = 0.3     # 突变率 (对标自发突变率)
P_DRIFT = 0.15       # 漂移保留率 (小群体随机)
P_NEUTRAL = 0.2      # 中性突变率
BOTTLENECK_EVERY = 5  # 每 N 轮瓶颈 (群体骤减)
REDUCE_THRESHOLD = 3  # 步骤 ≤3 冗余基因 → 缩减候选

STEP_ACTIONS = ["验证", "检查", "对比", "明确", "实现", "设计", "分析", "推导",
                "评估", "搜索", "提取", "汇总", "测试", "重构", "优化"]


def load_genes():
    """加载基因库 (state.json 或内置示例)"""
    if os.path.exists(STATE):
        try:
            with open(STATE, encoding="utf-8") as f:
                d = json.load(f)
            genes = d.get("genes", [])
            if genes and isinstance(genes[0], dict) and "steps" in genes[0]:
                return genes
        except Exception:
            pass
    # 内置示例基因 (推理步骤模板)
    return [
        {"id": "g1", "steps": ["明确目标", "分析约束", "设计方案", "实现验证"],
         "pass": 8, "fail": 2},
        {"id": "g2", "steps": ["搜索资料", "提取关键信息", "汇总对比", "输出结论"],
         "pass": 6, "fail": 4},
        {"id": "g3", "steps": ["推导公式", "数值验证", "对比基准"],
         "pass": 7, "fail": 1},
        {"id": "g4", "steps": ["拆解任务", "并行处理", "合并结果"],
         "pass": 5, "fail": 5},
        {"id": "g5", "steps": ["分析问题", "分析约束", "分析方案", "分析验证", "输出"],
         "pass": 3, "fail": 4},  # 冗余基因 (缩减候选)
    ]


# ── ① 随机变异 ──
def mutate(gene, rng):
    """随机变异: 步骤扰动 (替换/交换/新增/删除) — 对标自发突变"""
    g = copy.deepcopy(gene)
    steps = g.get("steps", [])
    if not steps:
        return g
    op = rng.random()
    if op < 0.4 and steps:  # 替换一步 (新操作)
        i = rng.randrange(len(steps))
        steps[i] = rng.choice(STEP_ACTIONS) + "优化步骤"
    elif op < 0.7 and len(steps) > 1:  # 交换两步 (重组)
        i, j = rng.sample(range(len(steps)), 2)
        steps[i], steps[j] = steps[j], steps[i]
    elif op < 0.9:  # 新增一步 (插入)
        steps.insert(rng.randrange(len(steps) + 1), rng.choice(STEP_ACTIONS))
    elif len(steps) > 2:  # 删除一步 (缺失突变)
        steps.pop(rng.randrange(len(steps)))
    g["steps"] = steps
    g["id"] = gene["id"] + "_m"
    return g


# ── ③ 遗传漂移 ──
def drift_pass(gene, rng):
    """遗传漂移: 低 fitness 基因以概率 P_DRIFT 保留
    (非适应性随机 — 小群体中中性基因漂移, 防过早收敛)"""
    p, f = gene.get("pass", 0), gene.get("fail", 0)
    fit = p / (p + f) if p + f > 0 else 0.5
    if fit < 0.4:  # 低分基因
        return rng.random() < P_DRIFT  # 随机保留 (漂移)
    return True  # 高分必留


# ── ④ 缩减演化 ──
def reductive_prune(gene):
    """缩减演化: 精简基因组 (删冗余低贡献步骤)
    对标: 寄生虫基因组缩减/细菌精简演化 (奥卡姆)"""
    g = copy.deepcopy(gene)
    steps = g.get("steps", [])
    # 冗余检测: 相同操作前缀连续 → 合并 (分析问题/分析约束 → 分析)
    merged = []
    for s in steps:
        op = s[:2]  # 操作名 (前 2 字: 分析/验证/检查...)
        if merged and op == merged[-1][:2]:
            continue  # 同操作重复 → 删
        merged.append(s)
    if len(merged) < len(steps):
        g["steps"] = merged
        g["id"] = gene["id"] + "_r"
        g["reduced"] = len(steps) - len(merged)
    return g


# ── ⑤ 中性突变 ──
def neutral_mutate(gene, rng):
    """中性突变: 不改变 fitness 的变异 (同义替换)
    对标: 密码子简并性 — 同义突变无表型效应但维持多样性"""
    g = copy.deepcopy(gene)
    steps = g.get("steps", [])
    if steps:
        i = rng.randrange(len(steps))
        # 同义替换: 保留语义, 换表述
        synonyms = {"验证": "校验", "检查": "核对", "分析": "剖析",
                    "设计": "规划", "实现": "落地", "搜索": "检索"}
        for k, v in synonyms.items():
            if k in steps[i]:
                steps[i] = steps[i].replace(k, v)
                break
    g["id"] = gene["id"] + "_n"
    return g


# ── ⑥ 瓶颈效应 ──
def bottleneck(pop, rng, keep_ratio=0.4):
    """瓶颈效应: 群体骤减 (保留 top + 随机) — 对标种群崩溃后恢复
    多样性骤降但适应型基因富集 (创始者效应)"""
    scored = sorted(pop, key=lambda g: -(g.get("pass", 0) /
                                         max(1, g.get("pass", 0) + g.get("fail", 0))))
    n_keep = max(2, int(len(pop) * keep_ratio))
    elites = scored[:max(1, n_keep // 2)]  # 精英一半
    rest = rng.sample(scored[n_keep // 2:], min(n_keep - len(elites), len(scored) - n_keep // 2)) if len(scored) > n_keep // 2 else []
    return elites + rest


# ── ⑦ 基因流 ──
def gene_flow(pop, external_genes, rng, flow_rate=0.2):
    """基因流: 外部基因引入 (跨域吸收) — 对标种群间迁移
    新基因替换同数量低分基因"""
    if not external_genes:
        return pop
    n_flow = max(1, int(len(pop) * flow_rate))
    # 换掉最低分基因
    pop_sorted = sorted(pop, key=lambda g: (g.get("pass", 0) /
                                            max(1, g.get("pass", 0) + g.get("fail", 0))))
    incoming = rng.sample(external_genes, min(n_flow, len(external_genes)))
    return pop_sorted[n_flow:] + incoming


# ── 演化主循环 ──
def evolve_round(pop, rng, external=None, round_no=1):
    """单轮演化: 选择→变异→漂移→缩减→中性→(瓶颈)→基因流"""
    new_pop = []
    # 自然选择 + 变异 (精英保留)
    scored = sorted(pop, key=lambda g: -(g.get("pass", 0) /
                                         max(1, g.get("pass", 0) + g.get("fail", 0))))
    elites = scored[:max(1, len(pop) // 3)]
    new_pop.extend(copy.deepcopy(e) for e in elites)
    # 变异池 (非精英)
    for g in scored[len(pop) // 3:]:
        if rng.random() < P_MUTATION:
            new_pop.append(mutate(g, rng))
        elif rng.random() < P_NEUTRAL:
            new_pop.append(neutral_mutate(g, rng))
        else:
            new_pop.append(copy.deepcopy(g))
    # 遗传漂移 (低分随机保留)
    new_pop = [g for g in new_pop if drift_pass(g, rng)]
    # 缩减演化 (精简冗余)
    new_pop = [reductive_prune(g) for g in new_pop]
    # 瓶颈效应 (每 N 轮)
    if round_no % BOTTLENECK_EVERY == 0:
        new_pop = bottleneck(new_pop, rng)
    # 基因流 (外部引入)
    if external:
        new_pop = gene_flow(new_pop, external, rng)
    # 保证非空
    if not new_pop:
        new_pop = copy.deepcopy(pop[:2])
    return new_pop


def pop_fitness(pop):
    return [g.get("pass", 0) / max(1, g.get("pass", 0) + g.get("fail", 0)) for g in pop]


def main():
    rng = random.Random(42)
    pop = load_genes()
    # 外部基因 (基因流来源 — 对标跨域吸收)
    external = [
        {"id": "ext1", "steps": ["假设提出", "实验设计", "数据验证", "结论提炼"],
         "pass": 9, "fail": 1},
        {"id": "ext2", "steps": ["问题定义", "方案对比", "风险分析", "实施反馈"],
         "pass": 7, "fail": 3},
    ]
    print("=== 基因演化引擎迭代 (7 演化逻辑) ===\n")
    print(f"初始种群: {len(pop)} 基因 | 适应度: "
          f"{[round(f, 2) for f in pop_fitness(pop)]}")
    for rnd in range(1, 7):
        pop = evolve_round(pop, rng, external=external, round_no=rnd)
        fits = pop_fitness(pop)
        n_reduced = sum(1 for g in pop if g.get("reduced"))
        print(f"轮 {rnd}: 种群 {len(pop)} | 适应度均值 {sum(fits)/len(fits):.2f} "
              f"| 缩减 {n_reduced} | 最佳 {max(fits):.2f}")
    # 最终验证: 多样性 + 适应度
    ids = {g["id"] for g in pop}
    print(f"\n最终: 种群 {len(pop)} | 独特基因 {len(ids)} | "
          f"适应度均值 {sum(pop_fitness(pop))/len(pop):.2f}")
    print("✅ 7 种演化逻辑已应用于迭代 (变异/选择/漂移/缩减/中性/瓶颈/基因流)")


if __name__ == "__main__":
    main()
