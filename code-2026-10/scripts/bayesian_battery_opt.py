#!/usr/bin/env python3
"""
贝叶斯优化 + 电池化成/老化工艺参数优化 (P1)

基于研究报告中 Bayesian Optimization 原理 (Attia et al. Nature 2020, Jiang et al. Applied Energy 2022)

输入: CSV文件包含化成/老化实验数据（参数列 + 目标列）
输出: 优化后的工艺参数建议 + 可视化

用法:
  python bayesian_battery_opt.py --data formation_data.csv --target k_value --params cc_current,cv_voltage,temperature,rest_time
  python bayesian_battery_opt.py --demo     # 演示模式
"""

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import Matern, RBF, ConstantKernel, WhiteKernel
    from scipy.optimize import minimize
    from scipy.stats import norm
except ImportError as e:
    print(f"❌ 依赖缺失: {e}")
    print("  安装: pip install numpy pandas scikit-learn scipy")
    sys.exit(1)

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
except ImportError:
    plt = None
    print("⚠ matplotlib 未安装, 跳过可视化")


class BayesianBatteryOptimizer:
    """贝叶斯优化器 —— 电池制造工艺参数优化"""

    def __init__(self, param_bounds: dict, kernel='matern', n_init=5):
        """
        param_bounds: {"cc_current": (0.5, 3.0), "temperature": (25, 60), ...}
        """
        self.param_names = list(param_bounds.keys())
        self.bounds = np.array([param_bounds[p] for p in self.param_names])
        self.n_dims = len(self.param_names)
        self.n_init = n_init

        # GP核函数 (Matern 5/2 适合电池工程这类中等光滑度的过程)
        if kernel == 'matern':
            self.kernel = ConstantKernel(1.0) * Matern(
                length_scale=np.ones(self.n_dims),
                length_scale_bounds=(1e-3, 100.0),
                nu=2.5
            ) + WhiteKernel(noise_level=0.1, noise_level_bounds=(1e-5, 1.0))
        else:
            self.kernel = ConstantKernel(1.0) * RBF(
                length_scale=np.ones(self.n_dims),
                length_scale_bounds=(1e-3, 100.0)
            ) + WhiteKernel(noise_level=0.1, noise_level_bounds=(1e-5, 1.0))

        self.gp = GaussianProcessRegressor(
            kernel=self.kernel,
            n_restarts_optimizer=10,
            alpha=1e-6,
            normalize_y=True
        )

        self.X = []  # 已评估参数
        self.y = []  # 已评估目标值
        self.iterations = 0

    def suggest(self, acquisition='ei'):
        """建议下一组待实验参数"""
        if len(self.X) < self.n_init:
            # 初始: Latin Hypercube 采样
            return self._latin_hypercube_sample()

        # GP 拟合
        X_arr = np.array(self.X)
        y_arr = np.array(self.y)
        self.gp.fit(X_arr, y_arr)

        # 采集函数优化 (多起点)
        best_x = None
        best_acq = -np.inf

        n_restarts = min(50, 20 * self.n_dims)
        for _ in range(n_restarts):
            x0 = np.random.uniform(self.bounds[:, 0], self.bounds[:, 1])
            res = minimize(
                lambda x: -self._acquisition(x.reshape(1, -1), acquisition),
                x0,
                bounds=self.bounds,
                method='L-BFGS-B'
            )
            acq_val = self._acquisition(res.x.reshape(1, -1), acquisition)
            if acq_val > best_acq:
                best_acq = acq_val
                best_x = res.x

        return best_x

    def _acquisition(self, x, method='ei'):
        """采集函数: Expected Improvement (EI)"""
        mu, sigma = self.gp.predict(x, return_std=True)
        y_best = np.min(self.y) if self.y else 0

        if method == 'ei':
            imp = y_best - mu
            with np.errstate(divide='warn'):
                z = imp / sigma
                ei = imp * norm.cdf(z) + sigma * norm.pdf(z)
                ei[sigma <= 0] = 0
            return ei.flatten()
        elif method == 'lcb':
            kappa = 2.0
            return -(mu - kappa * sigma).flatten()
        elif method == 'pi':
            imp = y_best - mu - 0.01
            z = imp / sigma
            return norm.cdf(z).flatten()
        return np.zeros(len(x))

    def add_observation(self, params: dict, target: float):
        """添加一组实验结果"""
        x = np.array([params[p] for p in self.param_names])
        self.X.append(x)
        self.y.append(target)
        self.iterations += 1

    def get_best(self) -> dict:
        """返回当前最优参数"""
        if not self.y:
            return {}
        best_idx = np.argmin(self.y)
        best_x = self.X[best_idx]
        return {
            "params": {p: float(best_x[i]) for i, p in enumerate(self.param_names)},
            "target": float(self.y[best_idx]),
            "iteration": int(best_idx + 1)
        }

    def predict(self, params: dict) -> tuple:
        """预测给定参数的目标值"""
        x = np.array([params[p] for p in self.param_names]).reshape(1, -1)
        mu, sigma = self.gp.predict(x, return_std=True)
        return float(mu[0]), float(sigma[0])

    def _latin_hypercube_sample(self):
        """初始: Latin Hypercube 采样"""
        n = len(self.X)
        segments = self.n_init
        points = np.zeros(self.n_dims)

        for d in range(self.n_dims):
            seg = (n % segments) / segments
            offset = np.random.uniform(0, 1/segments)
            points[d] = self.bounds[d, 0] + (seg + offset) * (self.bounds[d, 1] - self.bounds[d, 0])

        return points

    def plot_convergence(self, save_path: str = None):
        """绘制优化收敛曲线"""
        if plt is None or not self.y:
            return
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

        # 目标值随迭代变化
        ax1.plot(range(1, len(self.y)+1), self.y, 'b.-', label='评估值')
        best = np.minimum.accumulate(self.y) if self.y else []
        ax1.plot(range(1, len(best)+1), best, 'r-', linewidth=2, label='当前最优')
        ax1.set_xlabel('迭代次数')
        ax1.set_ylabel('目标值')
        ax1.set_title('优化收敛曲线')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # GP不确定性
        if len(self.X) > self.n_init:
            X_arr = np.array(self.X)
            y_arr = np.array(self.y)
            self.gp.fit(X_arr, y_arr)

            # 参数-目标散点图
            for i, name in enumerate(self.param_names):
                ax2.scatter(X_arr[:, i], y_arr, alpha=0.7, label=name)
            ax2.set_xlabel('参数值 (归一化)')
            ax2.set_ylabel('目标值')
            ax2.set_title('参数-目标关系')
            ax2.legend()
            ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        if save_path:
            plt.savefig(save_path, dpi=150)
            print(f"  📊 收敛图保存至: {save_path}")
        plt.close()


def run_demo():
    """演示模式：模拟化成工艺参数优化"""
    print("=" * 60)
    print("  贝叶斯优化演示: 电池化成工艺参数优化")
    print("=" * 60)

    # 参数空间
    param_bounds = {
        "cc_current_rate_C": (0.2, 2.0),    # CC阶段电流倍率
        "cv_voltage_V": (3.6, 4.2),          # CV截止电压
        "temperature_C": (25, 55),            # 化成温度
        "rest_time_min": (10, 60),            # 搁置时间
    }

    opt = BayesianBatteryOptimizer(param_bounds, kernel='matern', n_init=8)

    # 模拟真实化成实验
    print("\n📋 模拟 25 轮化成实验...\n")
    print(f"{'#':>3} | {'CC倍率':>8} | {'CV电压':>7} | {'温度℃':>5} | {'搁置min':>7} | {'K值(%/day)':>10}")
    print("-" * 55)

    for i in range(25):
        # 建议下组参数
        x_next = opt.suggest(acquisition='ei' if i >= opt.n_init else 'lcb')
        params = {p: float(x_next[j]) for j, p in enumerate(param_bounds.keys())}

        # 模拟实验: 真实函数 = (CC-1.0)^2 + (CV-3.85)^2/5 + (T-40)^2/100 + (rest-30)^2/500 + 噪声
        true_k = (
            (params["cc_current_rate_C"] - 1.0)**2 +
            (params["cv_voltage_V"] - 3.85)**2 / 5 +
            (params["temperature_C"] - 40)**2 / 100 +
            (params["rest_time_min"] - 30)**2 / 500
        )
        noise = np.random.normal(0, 0.03)
        k_value = true_k + noise

        opt.add_observation(params, k_value)

        print(f"{i+1:3d} | {params['cc_current_rate_C']:8.2f} | {params['cv_voltage_V']:7.3f} | "
              f"{params['temperature_C']:5.1f} | {params['rest_time_min']:7.1f} | {k_value:10.4f}")

    # 结果
    best = opt.get_best()
    print("\n" + "=" * 60)
    print("🏆 最优化成工艺参数:")
    for k, v in best["params"].items():
        print(f"  {k}: {v:.3f}")
    print(f"  预测K值: {best['target']:.4f} %/day")
    print(f"  最优轮次: #{best['iteration']}")
    print("=" * 60)

    # 保存
    import json
    output = {"best_params": best, "all_iterations": [
        {"params": {p: float(x[j]) for j, p in enumerate(param_bounds.keys())},
         "target": float(y)} for x, y in zip(opt.X, opt.y)
    ]}
    out_path = "D:/hermes/hermes-data/profiles/mybot/knowledge_base/reference/algorithm-research/bayes_opt_demo.json"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n📄 结果已保存至: {out_path}")

    # 可视化
    plot_path = "D:/hermes/hermes-data/profiles/mybot/knowledge_base/reference/algorithm-research/bayes_opt_convergence.png"
    opt.plot_convergence(save_path=plot_path)

    return best


def run_from_csv(csv_path: str, target_col: str, param_cols: list):
    """从CSV文件加载数据并优化"""
    df = pd.read_csv(csv_path)

    if target_col not in df.columns:
        print(f"❌ 目标列 '{target_col}' 不存在")
        return
    missing = [c for c in param_cols if c not in df.columns]
    if missing:
        print(f"❌ 参数列缺失: {missing}")
        return

    bounds = {}
    for col in param_cols:
        bounds[col] = (float(df[col].min()), float(df[col].max()))

    opt = BayesianBatteryOptimizer(bounds, kernel='matern', n_init=min(5, len(df)))

    target_is_k = 'k' in target_col.lower()
    for _, row in df.iterrows():
        params = {col: float(row[col]) for col in param_cols}
        target = float(row[target_col])
        if target_is_k:
            target = abs(target)  # K值越小越好
        opt.add_observation(params, target)

    # 优化和预测
    best = opt.get_best()
    print(f"\n🏆 最优参数 (基于{len(df)}组数据):")
    for k, v in best["params"].items():
        print(f"  {k}: {v:.3f}")
    print(f"  最优目标值: {best['target']:.4f}")

    return best


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="贝叶斯优化 — 电池化成工艺参数优化")
    parser.add_argument("--demo", action="store_true", help="演示模式")
    parser.add_argument("--data", help="CSV数据文件路径")
    parser.add_argument("--target", help="目标列名 (如 k_value)")
    parser.add_argument("--params", help="参数列名,逗号分隔 (如 cc_current,cv_voltage,temperature)")

    args = parser.parse_args()

    if args.demo:
        run_demo()
    elif args.data and args.target and args.params:
        run_from_csv(args.data, args.target, args.params.split(','))
    else:
        parser.print_help()
        print("\n示例:")
        print("  python bayesian_battery_opt.py --demo")
        print("  python bayesian_battery_opt.py --data formation.csv --target k_value --params cc_current,cv_voltage,temperature,rest_time")
