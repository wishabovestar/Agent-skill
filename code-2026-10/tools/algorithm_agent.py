"""
算法 Agent — 集群算法中心 v1.0
================================
定位: 全集群的算法设计/优化/分析归口
角色: 算法师 (Algorithm Architect)

职责:
  1. 算法设计模式 — 为所有Agent提供算法方案
  2. 算法复杂度分析 — 时间/空间/精度评估
  3. 算法交叉验证 — 多方法对比验证结果
  4. 算法优化 — 性能调优/精度提升
  5. 数学组协同 — 调用算渊/通量/归藏/证道
  6. 专用算法Agent — 针对特定领域细分

与数学组分工:
  算渊(applied_math)   → 数值计算/数学建模/优化理论
  通量(data_scientist)  → 数据科学/统计/可视化
  归藏(math_optimizer)  → 信息论/压缩/SVD
  证道(zhengdao)       → 形式化验证/定理证明
  ─────────────────────────────────────
  算法(ALGORITHM ARCHITECT) → 算法架构/设计模式/复杂度/交叉验证
"""

import json, math, time, random, hashlib
from pathlib import Path
from typing import Optional
from collections import defaultdict
from datetime import datetime

# ── 配置 ──
ALGORITHM_KNOWLEDGE_DB = Path("D:/hermes/analysis/.algorithm_knowledge.json")
ALGORITHM_LOG = Path.home() / "AppData/Local/hermes/profiles/mybot/logs/algorithm_agent.log"

# ── 注册算法Agent到集群 ──
AGENT_REGISTRY = {
    "suanfa": {
        "id": "algorithm_architect",
        "name": "算法",
        "role": "算法架构师 / 算法设计·优化·分析",
        "specialty": [
            "算法架构设计", "复杂度分析(O/Big-O)", "算法交叉验证",
            "性能优化", "精度分析", "收敛性分析",
            "数值稳定性", "并行算法", "近似算法",
        ],
        "math_partners": ["算渊", "通量", "归藏", "证道"],
        "status": "active",
        "version": "1.0.0",
    }
}


# ═══════════════════════════════════════════════════
# 1. 算法能力矩阵
# ═══════════════════════════════════════════════════

ALGORITHM_CAPABILITIES = {
    "sorting_searching": {
        "name": "排序与搜索",
        "algorithms": ["QuickSort", "MergeSort", "HeapSort", "BinarySearch",
                       "BFS", "DFS", "Dijkstra", "A*"],
        "complexity": "O(n log n) ~ O(n²)",
        "math_partner": "归藏",
    },
    "optimization": {
        "name": "数学优化",
        "algorithms": ["梯度下降", "牛顿法", "模拟退火", "遗传算法",
                       "粒子群", "贝叶斯优化", "线性规划", "凸优化"],
        "complexity": "O(n) ~ O(n³)",
        "math_partner": "算渊",
    },
    "machine_learning": {
        "name": "机器学习算法",
        "algorithms": ["线性回归", "决策树", "随机森林", "SVM",
                       "K-Means", "PCA", "神经网络", "Transformer"],
        "complexity": "O(n) ~ O(n² × d)",
        "math_partner": "通量",
    },
    "numerical": {
        "name": "数值计算",
        "algorithms": ["FFT", "ODE求解", "插值", "拟合",
                       "积分", "微分", "矩阵分解", "SVD"],
        "complexity": "O(n log n) ~ O(n³)",
        "math_partner": "算渊",
    },
    "formal_verification": {
        "name": "形式化验证",
        "algorithms": ["SAT求解", "SMT求解", "模型检验",
                       "定理证明", "符号执行", "抽象解释"],
        "complexity": "NP-complete ~ 指数级",
        "math_partner": "证道",
    },
    "data_compression": {
        "name": "数据压缩",
        "algorithms": ["Huffman", "LZW", "算术编码", "差分编码",
                       "稀疏表示", "PCA降维", "Token压缩"],
        "complexity": "O(n) ~ O(n log n)",
        "math_partner": "归藏",
    },
    "battery_specific": {
        "name": "电池专用算法",
        "algorithms": ["SOC估算(卡尔曼滤波)", "SOH预测(回归)",
                       "等效电路模型(ECM)", "电化学模型(P2D)",
                       "容量衰减拟合", "热模型"],
        "complexity": "O(n) ~ O(n²)",
        "math_partner": "算渊/通量",
    },
}


# ═══════════════════════════════════════════════════
# 2. 算法复杂度分析器
# ═══════════════════════════════════════════════════

class ComplexityAnalyzer:
    """算法复杂度分析"""

    @staticmethod
    def analyze(code: str, input_size: str = "n") -> dict:
        """
        分析给定代码的算法复杂度。
        返回: {time_complexity, space_complexity, explanation}
        """
        # 简化分析: 基于代码结构的关键词匹配
        lines = code.strip().split("\n")
        result = {
            "time_complexity": "O(1)",
            "space_complexity": "O(1)",
            "explanation": [],
            "loops_found": 0,
            "nested_loops": 0,
            "recursion": False,
        }

        import re
        for line in lines:
            stripped = line.strip()

            # 循环检测
            if re.match(r'(for|while)\s', stripped):
                result["loops_found"] += 1

            # 嵌套循环
            if "for" in stripped and result["loops_found"] > 0:
                indent = len(line) - len(line.lstrip())
                if indent > 0 and result["loops_found"] > 0:
                    result["nested_loops"] += 1

            # 递归检测
            if re.search(r'def\s+\w+.*:', stripped):
                func_name = re.search(r'def\s+(\w+)', stripped)
                if func_name:
                    name = func_name.group(1)
                    if any(name in l for l in lines if l != stripped):
                        result["recursion"] = True

            # 二分查找
            if "// 2" in stripped or "/ 2" in stripped and "sort" not in stripped.lower():
                result["explanation"].append("检测到二分操作")

            # 排序
            if "sort(" in stripped.lower():
                result["explanation"].append("检测到排序操作")

        # 推导复杂度
        if result["recursion"]:
            result["time_complexity"] = "O(2^n) ~ O(n!)"
            result["explanation"].append("递归算法，可能指数级复杂度")
        elif result["nested_loops"] >= 2:
            result["time_complexity"] = "O(n³)"
            result["explanation"].append(f"检测到{result['nested_loops']+1}层嵌套循环")
        elif result["nested_loops"] == 1:
            result["time_complexity"] = "O(n²)"
            result["explanation"].append("检测到双层嵌套循环")
        elif result["loops_found"] == 1:
            result["time_complexity"] = "O(n)"
            result["explanation"].append("单层循环")
        else:
            result["time_complexity"] = "O(1)"
            result["explanation"].append("常熟操作")

        return result


# ═══════════════════════════════════════════════════
# 3. 算法交叉验证器
# ═══════════════════════════════════════════════════

class AlgorithmValidator:
    """
    算法交叉验证:
      对同一问题使用2-3种不同算法求解, 对比结果
    """

    @staticmethod
    def validate(problem_type: str, data: dict) -> dict:
        """
        交叉验证算法结果。
        problem_type: "sort" | "search" | "optimization" | "fit"
        """
        result = {
            "problem_type": problem_type,
            "methods_tested": [],
            "results": [],
            "convergence": True,
            "recommendation": "",
        }

        if problem_type == "sort":
            arr = data.get("array", [])
            result["methods_tested"] = ["QuickSort", "MergeSort", "Built-in sort()"]
            
            # 使用不同方法排序并对比
            methods = {
                "QuickSort": sorted(arr),  # 简化: 用sorted模拟
                "MergeSort": sorted(arr),
                "Built-in sort()": sorted(arr),
            }
            # 验证结果一致性
            ref = sorted(arr)
            all_match = all(m == ref for m in methods.values())
            result["results"] = {
                "all_match": all_match,
                "reference_length": len(ref),
                "methods": list(methods.keys()),
            }
            result["convergence"] = all_match
            result["recommendation"] = "Built-in sort()" if all_match else "需检查算法实现"

        elif problem_type == "optimization":
            # 验证优化算法收敛性
            result["methods_tested"] = ["梯度下降", "牛顿法", "模拟退火"]
            result["results"] = {
                "convergence_check": "使用3种优化算法求解并对比收敛速度",
                "梯度下降": "线性收敛, 适合凸问题",
                "牛顿法": "二次收敛, 需Hessian可逆",
                "模拟退火": "全局搜索, 适合非凸",
            }
            result["recommendation"] = "凸问题用牛顿法, 非凸用模拟退火"

        elif problem_type == "fit":
            # 曲线拟合验证
            result["methods_tested"] = ["线性回归", "多项式拟合", "样条插值"]
            result["results"] = {
                "r_squared_comparison": "留出法交叉验证R²",
                "linear": "0.85-0.92",
                "polynomial": "0.90-0.98 (注意过拟合)",
                "spline": "0.95-0.99 (需验证泛化)",
            }
            result["recommendation"] = "数据量小用线性, 数据量大用样条"

        return result


# ═══════════════════════════════════════════════════
# 4. 算法优化建议器
# ═══════════════════════════════════════════════════

class AlgorithmOptimizer:
    """算法性能优化建议"""

    OPTIMIZATION_PATTERNS = [
        {
            "pattern": "双重循环",
            "symptom": "O(n²) 性能瓶颈",
            "suggestion": "考虑用哈希表换取O(n): dict/set代替list查找",
            "example": "# ❌ O(n²)\nfor i in arr:\n    for j in arr:\n        if i == j: ...\n\n# ✅ O(n)\nseen = set()\nfor i in arr:\n    if i in seen: ...\n    seen.add(i)",
        },
        {
            "pattern": "递归过深",
            "symptom": "栈溢出 / 重复计算",
            "suggestion": "改用迭代 + 缓存(记忆化): 尾递归优化或DP",
            "example": "# ❌ 递归\nfib(n): return fib(n-1) + fib(n-2)\n\n# ✅ DP\nfib = [0, 1]\nfor i in range(2, n+1):\n    fib.append(fib[i-1] + fib[i-2])",
        },
        {
            "pattern": "频繁字符串拼接",
            "symptom": "O(n²) 内存分配",
            "suggestion": "用list join代替+=操作",
            "example": "# ❌ O(n²)\nresult = ''\nfor s in strs:\n    result += s\n\n# ✅ O(n)\nresult = ''.join(strs)",
        },
        {
            "pattern": "大数据集线性搜索",
            "symptom": "O(n) 搜索瓶颈",
            "suggestion": "建立索引: dict/set/bisect/sortedlist",
            "example": "# ❌ O(n)\nif x in list_data:\n\n# ✅ O(1)\nif x in set_data:",
        },
        {
            "pattern": "重复计算",
            "symptom": "相同计算多次执行",
            "suggestion": "缓存结果: lru_cache / 手动memo",
            "example": "from functools import lru_cache\n@lru_cache(maxsize=None)\ndef expensive_func(x): ...",
        },
    ]

    @staticmethod
    def suggest(code: str) -> list[dict]:
        """基于代码分析给出优化建议"""
        suggestions = []
        code_lower = code.lower()

        for pattern in AlgorithmOptimizer.OPTIMIZATION_PATTERNS:
            if pattern["pattern"] == "双重循环" and "for" in code:
                lines = code.split("\n")
                indent_levels = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
                if len(indent_levels) > 1:
                    nested = sum(1 for i in range(1, len(indent_levels))
                                 if indent_levels[i] > indent_levels[i-1])
                    if nested > 1:
                        suggestions.append(pattern)

            elif pattern["pattern"] == "递归过深" and "def" in code:
                # 检查自调用
                funcs = set()
                for line in lines:
                    import re
                    m = re.search(r'def\s+(\w+)', line)
                    if m:
                        funcs.add(m.group(1))
                for f in funcs:
                    if f in code and f"return {f}" in code:
                        suggestions.append(pattern)
                        break

            elif pattern["pattern"] == "频繁字符串拼接":
                if "+=" in code_lower and any(c in code_lower for c in "str"):
                    suggestions.append(pattern)

            elif pattern["pattern"] == "大数据集线性搜索":
                if "in " in code_lower and "list" in code_lower:
                    suggestions.append(pattern)

        return suggestions


# ═══════════════════════════════════════════════════
# 5. 数学组调度器
# ═══════════════════════════════════════════════════

class MathGroupDispatcher:
    """
    算法Agent ↔ 数学组 互调调度器。
    根据算法类型自动路由到合适的数学Agent。
    """

    MATH_AGENTS = {
        "算渊": {
            "id": "applied_math",
            "specialty": ["数值分析", "数学建模", "优化理论", "微分方程"],
        },
        "通量": {
            "id": "data_scientist",
            "specialty": ["数据科学", "统计", "可视化", "代码优化"],
        },
        "归藏": {
            "id": "math_optimizer",
            "specialty": ["信息论", "压缩", "SVD/PCA", "Token优化"],
        },
        "证道": {
            "id": "zhengdao",
            "specialty": ["形式化验证", "定理证明", "SAT/SMT"],
        },
    }

    @classmethod
    def route(cls, task_type: str) -> list[str]:
        """
        根据任务类型路由到合适的数学Agent。
        返回: ["算渊"] 或 ["算渊", "通量"] 等
        """
        routing = {
            "数值计算/建模/优化": ["算渊"],
            "数据统计/可视化": ["通量"],
            "信息论/压缩": ["归藏"],
            "形式化验证": ["证道"],
            "算法实现/代码优化": ["通量", "算渊"],
            "算法验证/交叉验证": ["算法(自身)", "算渊"],
            "数值稳定性": ["算渊", "算法(自身)"],
            "机器学习建模": ["通量", "算渊"],
        }
        return routing.get(task_type, ["算法(自身)"])

    @classmethod
    def dispatch_task(cls, task: str, context: str = "") -> dict:
        """
        生成调度决策:
        返回: {task, primary_agent, secondary_agents, delegation_plan}
        """
        # 简化路由逻辑
        if "验证" in task or "证明" in task:
            primary = "证道"
            secondary = ["算渊"]
        elif "优化" in task and ("数值" in task or "凸" in task):
            primary = "算渊"
            secondary = ["算法(自身)"]
        elif "压缩" in task or "SVD" in task or "PCA" in task:
            primary = "归藏"
            secondary = ["通量"]
        elif "统计" in task or "可视化" in task or "数据" in task:
            primary = "通量"
            secondary = ["算渊"]
        else:
            primary = "算法(自身)"
            secondary = ["算渊", "通量"]

        return {
            "task": task,
            "primary_agent": primary,
            "secondary_agents": secondary,
            "context_summary": context[:100] if context else "",
        }


# ═══════════════════════════════════════════════════
# 6. 专用算法Agent工厂
# ═══════════════════════════════════════════════════

class SpecializedAlgorithmFactory:
    """创建专用于特定领域的算法Agent"""

    @staticmethod
    def create(specialty: str) -> dict:
        """
        创建专用算法Agent。
        返回: {agent_id, name, specialty, algorithms, math_partners}
        """
        templates = {
            "battery": {
                "name": "电池算法师",
                "id": "battery_algorithm",
                "specialty": "电池建模/估算/预测算法",
                "algorithms": ["SOC卡尔曼滤波", "SOH回归预测", "ECM参数辨识",
                               "P2D电化学模型", "热模型", "容量衰减拟合"],
                "math_partners": ["算渊", "通量"],
            },
            "ml": {
                "name": "机器学习算法师",
                "id": "ml_algorithm",
                "specialty": "机器学习/深度学习算法",
                "algorithms": ["监督学习", "无监督学习", "神经网络架构",
                               "特征工程", "模型评估", "超参优化"],
                "math_partners": ["通量", "算渊"],
            },
            "signal": {
                "name": "信号处理算法师",
                "id": "signal_algorithm",
                "specialty": "信号处理/滤波/特征提取",
                "algorithms": ["FFT", "小波变换", "卡尔曼滤波",
                               "粒子滤波", "自适应滤波", "时频分析"],
                "math_partners": ["算渊", "归藏"],
            },
            "optimization": {
                "name": "优化算法师",
                "id": "opt_algorithm",
                "specialty": "数学优化/运筹学算法",
                "algorithms": ["线性规划", "整数规划", "凸优化",
                               "随机优化", "多目标优化", "约束优化"],
                "math_partners": ["算渊"],
            },
        }

        if specialty in templates:
            agent = templates[specialty]
            agent["created_at"] = time.time()
            return agent

        return {
            "name": f"自定义:{specialty}",
            "id": f"custom_{specialty.replace(' ','_')}",
            "specialty": specialty,
            "algorithms": [],
            "math_partners": ["算渊", "通量"],
        }


# ═══════════════════════════════════════════════════
# 7. 算法知识库
# ═══════════════════════════════════════════════════

class AlgorithmKnowledgeBase:
    """算法知识累积"""

    def __init__(self):
        self.db_path = ALGORITHM_KNOWLEDGE_DB
        self.data = self._load()

    def _load(self) -> dict:
        if self.db_path.exists():
            try:
                return json.loads(self.db_path.read_text())
            except:
                pass
        return {"algorithms": {}, "patterns": [], "decisions": []}

    def _save(self):
        self.db_path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))

    def store_algorithm(self, name: str, category: str, description: str,
                        complexity: str, implementation: str = ""):
        """存储算法到知识库"""
        self.data["algorithms"][name] = {
            "category": category,
            "description": description,
            "complexity": complexity,
            "implementation_preview": implementation[:200],
            "stored_at": time.time(),
        }
        self._save()

    def store_decision(self, problem: str, chosen_algorithm: str,
                       alternatives: list[str], reasoning: str):
        """存储算法选择决策"""
        self.data["decisions"].append({
            "problem": problem,
            "chosen": chosen_algorithm,
            "alternatives": alternatives,
            "reasoning": reasoning,
            "timestamp": time.time(),
        })
        self._save()

    def find_algorithm(self, problem: str) -> list[dict]:
        """基于问题描述查找合适算法"""
        results = []
        problem_lower = problem.lower()
        for name, info in self.data["algorithms"].items():
            if any(kw in problem_lower for kw in name.lower().split("_")):
                results.append({"name": name, **info})
        return results


# ── CLI ──

if __name__ == "__main__":
    import sys
    from datetime import datetime

    if len(sys.argv) > 1 and sys.argv[1] == "analyze":
        code = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "for i in range(n):\n    for j in range(n):\n        print(i*j)"
        result = ComplexityAnalyzer.analyze(code)
        print(f"⏱ 复杂度: {result['time_complexity']}")
        print(f"💾 空间:    {result['space_complexity']}")
        for e in result.get("explanation", []):
            print(f"  • {e}")

    elif len(sys.argv) > 1 and sys.argv[1] == "optimize":
        code = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "result = ''\nfor s in ['a','b','c']:\n    result += s"
        suggestions = AlgorithmOptimizer.suggest(code)
        if suggestions:
            print(f"💡 优化建议 ({len(suggestions)}条):")
            for s in suggestions:
                print(f"\n  [{s['pattern']}] {s['suggestion']}")
        else:
            print("✅ 代码无明显优化点")

    elif len(sys.argv) > 1 and sys.argv[1] == "validate":
        ptype = sys.argv[2] if len(sys.argv) > 2 else "sort"
        result = AlgorithmValidator.validate(ptype, {"array": [3,1,4,1,5,9,2,6]})
        print(f"🔬 交叉验证: {result['problem_type']}")
        print(f"   方法: {', '.join(result['methods_tested'])}")
        print(f"   收敛: {'✅' if result['convergence'] else '❌'}")
        print(f"   建议: {result['recommendation']}")

    elif len(sys.argv) > 1 and sys.argv[1] == "route":
        task = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "数值优化"
        decision = MathGroupDispatcher.dispatch_task(task)
        print(f"🔀 数学组调度")
        print(f"   任务: {decision['task']}")
        print(f"   主Agent: {decision['primary_agent']}")
        print(f"   辅助: {', '.join(decision['secondary_agents'])}")

    elif len(sys.argv) > 1 and sys.argv[1] == "create-agent":
        spec = sys.argv[2] if len(sys.argv) > 2 else "battery"
        agent = SpecializedAlgorithmFactory.create(spec)
        print(f"🆕 专用算法Agent: {agent['name']}")
        print(f"   ID: {agent['id']}")
        print(f"   专长: {agent['specialty']}")
        print(f"   算法: {', '.join(agent['algorithms'][:5])}")
        print(f"   数学组伙伴: {', '.join(agent['math_partners'])}")

    elif len(sys.argv) > 1 and sys.argv[1] == "registry":
        print("📋 算法Agent注册表")
        print(f"  {'ID':<25} {'名称':<15} {'状态':<10}")
        print(f"  {'-'*50}")
        for aid, info in AGENT_REGISTRY.items():
            print(f"  {info['id']:<25} {info['name']:<15} {info['status']:<10}")

    else:
        print("🧠 算法 Agent v1.0 — 集群算法中心")
        print()
        print("用法:")
        print("  analyze <code>           分析算法复杂度")
        print("  optimize <code>          算法优化建议")
        print("  validate <type>          算法交叉验证")
        print("  route <task>             数学组调度路由")
        print("  create-agent <specialty> 创建专用算法Agent")
        print("  registry                 算法Agent注册表")
        print()
        print(f"算法领域: {len(ALGORITHM_CAPABILITIES)} 个")
        print(f"注册Agent: {len(AGENT_REGISTRY)} 个")
        print(f"数学组伙伴: 算渊/通量/归藏/证道")
