#!/usr/bin/env python3
"""
粒子群优化 (PSO) 电池等效电路模型 (ECM) 参数辨识 (P3)

基于研究报告中 PSO 算法原理 (Kennedy & Eberhart 1995)
及 ECM 参数辨识应用 (Rahman et al. 2016, Białoń et al. 2023)

模型: 二阶 RC 等效电路模型
  - R0: 欧姆内阻
  - R1, C1: 电化学极化
  - R2, C2: 浓度极化

用法:
  python pso_ecm_identifier.py --demo           # 演示模式
  python pso_ecm_identifier.py --data pulse.csv --current-col I --voltage-col V
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
except ImportError:
    print("❌ 请安装: pip install numpy pandas")
    sys.exit(1)


class Particle:
    """PSO 粒子"""

    def __init__(self, dim, bounds):
        self.position = np.array([np.random.uniform(b[0], b[1]) for b in bounds])
        self.velocity = np.random.uniform(-0.1, 0.1, dim)
        self.best_position = self.position.copy()
        self.best_fitness = float('inf')
        self.fitness = float('inf')


class PSOptimizer:
    """粒子群优化器"""

    def __init__(self, dim, bounds, n_particles=50, max_iter=200,
                 w=0.72, c1=1.49, c2=1.49):
        self.dim = dim
        self.bounds = bounds
        self.n_particles = n_particles
        self.max_iter = max_iter
        self.w = w          # 惯性权重
        self.c1 = c1        # 认知系数
        self.c2 = c2        # 社会系数

        self.swarm = [Particle(dim, bounds) for _ in range(n_particles)]
        self.gbest_position = self.swarm[0].position.copy()
        self.gbest_fitness = float('inf')
        self.convergence = []

    def optimize(self, fitness_fn, verbose=True):
        """执行 PSO 优化"""
        for it in range(self.max_iter):
            for p in self.swarm:
                # 评估
                p.fitness = fitness_fn(p.position)
                if p.fitness < p.best_fitness:
                    p.best_fitness = p.fitness
                    p.best_position = p.position.copy()
                if p.fitness < self.gbest_fitness:
                    self.gbest_fitness = p.fitness
                    self.gbest_position = p.position.copy()

                # 速度更新 (带惯性权重衰减)
                w_it = self.w * (1 - it / self.max_iter)
                r1, r2 = np.random.rand(2)
                p.velocity = (w_it * p.velocity +
                              self.c1 * r1 * (p.best_position - p.position) +
                              self.c2 * r2 * (self.gbest_position - p.position))

                # 位置更新
                p.position += p.velocity
                # 边界约束
                for d in range(self.dim):
                    p.position[d] = np.clip(p.position[d],
                                            self.bounds[d][0],
                                            self.bounds[d][1])

            self.convergence.append(self.gbest_fitness)
            if verbose and (it % 20 == 0 or it == self.max_iter - 1):
                print(f"  iter {it:3d}: fitness={self.gbest_fitness:.6e}")

        return self.gbest_position, self.gbest_fitness


class SecondOrderECM:
    """二阶 RC 等效电路模型"""

    def __init__(self, dt=1.0):
        self.dt = dt

    def simulate(self, current, params, initial_v=None):
        """
        仿真电池端电压响应

        params: [R0, R1, C1, R2, C2] 
        current: 电流序列 (A, 正=放电)
        """
        R0, R1, C1, R2, C2 = params
        tau1, tau2 = R1 * C1, R2 * C2
        n = len(current)

        V1 = np.zeros(n)  # RC1 电压
        V2 = np.zeros(n)  # RC2 电压
        Vt = np.zeros(n)  # 端电压

        # 初始条件
        ocv = initial_v if initial_v else 3.7

        for k in range(n):
            I = current[k]
            # RC 网络响应 (一阶离散化)
            if k > 0:
                V1[k] = V1[k-1] * np.exp(-self.dt/tau1) + R1 * I * (1 - np.exp(-self.dt/tau1))
                V2[k] = V2[k-1] * np.exp(-self.dt/tau2) + R2 * I * (1 - np.exp(-self.dt/tau2))
            else:
                V1[k] = R1 * I * (1 - np.exp(-self.dt/tau1))
                V2[k] = R2 * I * (1 - np.exp(-self.dt/tau2))

            Vt[k] = ocv - I * R0 - V1[k] - V2[k]

        return Vt


def generate_pulse_test():
    """生成 HPPC 脉冲测试模拟数据"""
    dt = 1.0
    t_total = 600  # 10分钟

    # 真实参数
    true_params = [0.02, 0.005, 2000, 0.003, 8000]  # R0, R1, C1, R2, C2
    ecm = SecondOrderECM(dt)

    # 脉冲电流曲线: 静止→1C放电→静止→1C充电→静止
    I = np.zeros(t_total)
    I[60:120] = 5.0     # 1C 放电 60s
    I[180:240] = -5.0   # 1C 充电 60s

    V = ecm.simulate(I, true_params, initial_v=3.7)
    V_noisy = V + np.random.normal(0, 0.002, len(V))  # 2mV 噪声

    return I, V, V_noisy, true_params, dt


def run_demo():
    """演示模式"""
    print("=" * 60)
    print("  PSO-ECM 电池参数辨识演示")
    print("=" * 60)

    # 生成脉冲测试数据
    I, V_clean, V_noisy, true_params, dt = generate_pulse_test()
    true_R0, true_R1, true_C1, true_R2, true_C2 = true_params
    print(f"\n📊 模拟 HPPC 脉冲测试: {len(I)}s, dt={dt}s")
    print(f"  真实参数: R0={true_R0:.4f}Ω  R1={true_R1:.4f}Ω  C1={true_C1:.0f}F")
    print(f"                     R2={true_R2:.4f}Ω  C2={true_C2:.0f}F")

    # PSO 参数辨识
    print("\n🔍 PSO 优化中 (200代, 50粒子)...")
    dim = 5
    bounds = [
        (0.001, 0.1),     # R0
        (0.0001, 0.05),   # R1
        (100, 10000),     # C1
        (0.0001, 0.05),   # R2
        (100, 50000),     # C2
    ]

    ecm = SecondOrderECM(dt)

    def fitness_fn(params):
        V_pred = ecm.simulate(I, params, initial_v=3.7)
        return np.mean((V_noisy - V_pred) ** 2)

    pso = PSOptimizer(dim, bounds, n_particles=50, max_iter=200)
    best_params, best_fit = pso.optimize(fitness_fn, verbose=True)

    R0, R1, C1, R2, C2 = best_params
    print(f"\n🏆 辨识结果:")
    print(f"  {'参数':>8} | {'真实值':>12} | {'辨识值':>12} | {'误差%':>8}")
    print(f"  {'R0(Ω)':>8} | {true_R0:>12.4f} | {R0:>12.4f} | {abs(R0-true_R0)/true_R0*100:>7.1f}%")
    print(f"  {'R1(Ω)':>8} | {true_R1:>12.4f} | {R1:>12.4f} | {abs(R1-true_R1)/true_R1*100:>7.1f}%")
    print(f"  {'C1(F)':>8} | {true_C1:>12.0f} | {C1:>12.0f} | {abs(C1-true_C1)/true_C1*100:>7.1f}%")
    print(f"  {'R2(Ω)':>8} | {true_R2:>12.4f} | {R2:>12.4f} | {abs(R2-true_R2)/true_R2*100:>7.1f}%")
    print(f"  {'C2(F)':>8} | {true_C2:>12.0f} | {C2:>12.0f} | {abs(C2-true_C2)/true_C2*100:>7.1f}%")
    print(f"\n  MSE = {best_fit:.6e}")

    # 验证: 用辨识参数重仿真
    V_pred = ecm.simulate(I, best_params, initial_v=3.7)
    rmse = np.sqrt(np.mean((V_noisy - V_pred)**2)) * 1000  # mV
    print(f"  RMSE = {rmse:.2f} mV")

    # 保存结果
    results = {
        "true_params": {
            "R0": true_R0, "R1": true_R1, "C1": true_C1,
            "R2": true_R2, "C2": true_C2
        },
        "identified_params": {
            "R0": float(R0), "R1": float(R1), "C1": float(C1),
            "R2": float(R2), "C2": float(C2)
        },
        "fitness_mse": float(best_fit),
        "rmse_mV": float(rmse),
        "convergence": [float(f) for f in pso.convergence],
    }
    out_path = "D:/hermes/hermes-data/profiles/mybot/knowledge_base/reference/algorithm-research/pso_ecm_demo.json"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n📄 结果已保存至: {out_path}")

    # 收敛图
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

        # 收敛曲线
        ax1.semilogy(pso.convergence)
        ax1.set_xlabel('迭代次数')
        ax1.set_ylabel('MSE')
        ax1.set_title('PSO 收敛曲线')
        ax1.grid(True, alpha=0.3)

        # 电压对比
        t = np.arange(len(I))
        ax2.plot(t, V_noisy, 'b-', alpha=0.5, label='测量电压 (含噪声)')
        ax2.plot(t, V_pred, 'r--', linewidth=2, label='辨识模型仿真')
        ax2.set_xlabel('时间 (s)')
        ax2.set_ylabel('电压 (V)')
        ax2.set_title(f'电压拟合 (RMSE={rmse:.2f} mV)')
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        plot_path = "D:/hermes/hermes-data/profiles/mybot/knowledge_base/reference/algorithm-research/pso_ecm_fit.png"
        plt.savefig(plot_path, dpi=150)
        print(f"  📊 拟合图保存至: {plot_path}")
        plt.close()
    except ImportError:
        pass

    return results


def run_from_csv(csv_path: str, current_col: str, voltage_col: str, dt: float = 1.0):
    """从真实脉冲测试数据辨识"""
    df = pd.read_csv(csv_path)
    I = df[current_col].values
    V = df[voltage_col].values

    print(f"📊 加载数据: {len(df)} 点, dt={dt}s")

    dim = 5
    R0_max = float(np.max(np.abs(np.diff(V) / np.diff(I, prepend=0)))) if len(I) > 1 else 0.1
    bounds = [
        (R0_max*0.1, R0_max*2),
        (0.0001, 0.05),
        (100, 10000),
        (0.0001, 0.05),
        (100, 50000),
    ]

    ecm = SecondOrderECM(dt)

    def fitness_fn(params):
        V_pred = ecm.simulate(I, params, initial_v=float(V[0]))
        return np.mean((V - V_pred) ** 2)

    print("🔍 PSO 优化中...")
    pso = PSOptimizer(dim, bounds, n_particles=50, max_iter=200)
    best_params, best_fit = pso.optimize(fitness_fn, verbose=True)

    R0, R1, C1, R2, C2 = best_params
    print(f"\n🏆 辨识结果:")
    print(f"  R0={R0:.4f}Ω, R1={R1:.4f}Ω, C1={C1:.0f}F")
    print(f"  R2={R2:.4f}Ω, C2={C2:.0f}F")
    print(f"  MSE={best_fit:.6e}")

    return best_params


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PSO-ECM 电池参数辨识")
    parser.add_argument("--demo", action="store_true", help="演示模式")
    parser.add_argument("--data", help="脉冲测试CSV文件")
    parser.add_argument("--current-col", default="I", help="电流列名")
    parser.add_argument("--voltage-col", default="V", help="电压列名")
    parser.add_argument("--dt", type=float, default=1.0, help="采样间隔 (s)")

    args = parser.parse_args()

    if args.demo:
        run_demo()
    elif args.data:
        run_from_csv(args.data, args.current_col, args.voltage_col, args.dt)
    else:
        parser.print_help()
        print("\n示例:")
        print("  python pso_ecm_identifier.py --demo")
        print("  python pso_ecm_identifier.py --data hppc_test.csv --current-col I --voltage-col V")
