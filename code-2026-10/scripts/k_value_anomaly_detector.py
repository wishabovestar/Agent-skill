#!/usr/bin/env python3
"""
K值离散分析与异常检测 (P2)

基于研究报告中 Isolation Forest / LOF / Autoencoder 异常检测原理
(Liu et al. ICDM 2008, Breunig et al. ACM SIGMOD 2000)

输入: 电池分选数据 CSV (K值、电压、内阻、容量等)
输出: 异常电池识别 + 分选阈值建议 + 可视化

用法:
  python k_value_anomaly_detector.py --data battery_sorting.csv --k-col k_value
  python k_value_anomaly_detector.py --demo
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import IsolationForest
    from sklearn.neighbors import LocalOutlierFactor
    from sklearn.preprocessing import StandardScaler
except ImportError as e:
    print(f"❌ 依赖缺失: {e}")
    print("  安装: pip install numpy pandas scikit-learn")
    sys.exit(1)

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
except ImportError:
    plt = None


class KValueAnomalyDetector:
    """K值离散分析与分选优化"""

    def __init__(self, contamination=0.05):
        self.contamination = contamination
        self.scaler = StandardScaler()
        self.iso_forest = IsolationForest(
            n_estimators=200,
            contamination=contamination,
            random_state=42,
            bootstrap=True
        )
        self.lof = LocalOutlierFactor(
            n_neighbors=20,
            contamination=contamination,
            novelty=False
        )
        self.results = {}

    def analyze(self, df: pd.DataFrame, k_col: str, feature_cols: list = None):
        """
        执行 K 值离散分析

        Args:
            df: DataFrame with battery data
            k_col: K值列名
            feature_cols: 参与异常检测的特征列 (默认 K值+电压+内阻+容量)
        """
        if feature_cols is None:
            # 自动选择数值列
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            feature_cols = [c for c in numeric_cols if c != k_col][:5]

        # 检查必须列
        required = [k_col] + feature_cols
        missing = [c for c in required if c not in df.columns]
        if missing:
            print(f"❌ 缺少列: {missing}")
            return

        # 清洗
        data = df[required].dropna().copy()
        n_original = len(df)
        n_clean = len(data)
        print(f"  原始数据: {n_original} 条, 清洗后: {n_clean} 条 (移除 {n_original-n_clean} 条空值)")

        # K 值统计
        k_values = data[k_col].values
        stats = {
            "mean": float(np.mean(k_values)),
            "std": float(np.std(k_values)),
            "median": float(np.median(k_values)),
            "q1": float(np.percentile(k_values, 25)),
            "q3": float(np.percentile(k_values, 75)),
            "min": float(np.min(k_values)),
            "max": float(np.max(k_values)),
            "cv": float(np.std(k_values) / max(abs(np.mean(k_values)), 1e-6)),  # 变异系数
            "p90": float(np.percentile(k_values, 90)),
            "p95": float(np.percentile(k_values, 95)),
            "p99": float(np.percentile(k_values, 99)),
        }
        self.results["k_value_stats"] = stats

        print(f"\n  K值统计:")
        print(f"    均值={stats['mean']:.4f}, 中位数={stats['median']:.4f}")
        print(f"    标准差={stats['std']:.4f}, 变异系数(CV)={stats['cv']:.2%}")
        print(f"    Q1={stats['q1']:.4f}, Q3={stats['q3']:.4f}")
        print(f"    95分位={stats['p95']:.4f}, 99分位={stats['p99']:.4f}")

        # 归一化
        X = self.scaler.fit_transform(data[feature_cols + [k_col]].values)

        # Isolation Forest 异常检测
        iso_pred = self.iso_forest.fit_predict(X)
        iso_score = self.iso_forest.score_samples(X)
        data['iso_pred'] = iso_pred
        data['iso_score'] = iso_score

        # LOF 异常检测
        lof_pred = self.lof.fit_predict(X)
        lof_score = self.lof.negative_outlier_factor_
        data['lof_pred'] = lof_pred
        data['lof_score'] = lof_score

        # 综合异常评分 (两种方法投票)
        data['ensemble_anomaly'] = ((data['iso_pred'] == -1) | (data['lof_pred'] == -1))
        data['ensemble_score'] = (
            -data['iso_score'] / max(abs(data['iso_score'])) +
            -data['lof_score'] / max(abs(data['lof_score']))
        ) / 2

        n_anomalies = int(data['ensemble_anomaly'].sum())
        print(f"\n  🚨 检测到异常电池: {n_anomalies} / {n_clean} ({n_anomalies/n_clean*100:.1f}%)")

        # 分选阈值建议 (基于K值)
        k_sorted = np.sort(k_values)
        n = len(k_sorted)

        # IQR法阈值
        iqr = stats['q3'] - stats['q1']
        iqr_lower = stats['q1'] - 1.5 * iqr
        iqr_upper = stats['q3'] + 1.5 * iqr

        # 3-sigma 法阈值
        sigma_upper = stats['mean'] + 3 * stats['std']
        sigma_lower = stats['mean'] - 3 * stats['std']

        # 百分位法阈值
        p1_lower = stats['p99']  # 高K值端
        p5_lower = stats['p95']

        thresholds = {
            "iqr_method": {"lower": round(iqr_lower, 4), "upper": round(iqr_upper, 4)},
            "sigma_3": {"lower": round(sigma_lower, 4), "upper": round(sigma_upper, 4)},
            "p95_threshold": round(p5_lower, 4),
            "p99_threshold": round(p1_lower, 4),
            "recommended_k_max": round(min(iqr_upper, sigma_upper), 4),
        }
        self.results["thresholds"] = thresholds

        print(f"\n  📊 分选阈值建议:")
        print(f"    IQR法: [{iqr_lower:.4f}, {iqr_upper:.4f}]")
        print(f"    3-Sigma法: [{sigma_lower:.4f}, {sigma_upper:.4f}]")
        print(f"    推荐K值上界: {thresholds['recommended_k_max']:.4f}")

        # 如果原始数据有分级列，评估分级效果
        grade_cols = [c for c in df.columns if 'grade' in c.lower() or 'level' in c.lower() or 'bin' in c.lower()]
        if grade_cols:
            grade_col = grade_cols[0]
            merged = data.merge(df[[grade_col]], left_index=True, right_index=True, how='left')
            grade_stats = merged.groupby(grade_col)[k_col].describe()
            self.results["grade_analysis"] = grade_stats.to_dict()
            print(f"\n  当前分级 {grade_col} 的K值分布:")
            for grade in grade_stats.index:
                g = grade_stats.loc[grade]
                print(f"    {grade}: n={int(g['count']):3d}, mean={g['mean']:.4f}, "
                      f"std={g['std']:.4f}, [{g['min']:.4f}, {g['max']:.4f}]")

        self.results["anomaly_count"] = int(n_anomalies)
        self.results["total_count"] = n_clean
        self.results["anomaly_rate"] = n_anomalies / n_clean if n_clean else 0
        self.data = data
        self.k_col = k_col
        self.feature_cols = feature_cols

        return self.results

    def plot_results(self, save_path: str = None):
        """生成可视化"""
        if plt is None or not hasattr(self, 'data'):
            return

        data = self.data
        k_col = self.k_col

        fig, axes = plt.subplots(2, 3, figsize=(18, 10))

        # 1. K值直方图
        ax = axes[0, 0]
        ax.hist(data[k_col], bins=50, alpha=0.7, color='steelblue', edgecolor='white')
        ax.axvline(np.mean(data[k_col]), color='red', linestyle='--', label=f'均值={np.mean(data[k_col]):.3f}')
        ax.axvline(np.median(data[k_col]), color='green', linestyle='--', label=f'中位数={np.median(data[k_col]):.3f}')
        ax.set_xlabel('K值 (%/day)')
        ax.set_ylabel('频数')
        ax.set_title('K值分布')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

        # 2. K值箱线图
        ax = axes[0, 1]
        bp = ax.boxplot(data[k_col], vert=True, patch_artist=True)
        bp['boxes'][0].set_facecolor('lightblue')
        ax.set_ylabel('K值 (%/day)')
        ax.set_title('K值箱线图 (异常点=o)')
        ax.grid(True, alpha=0.3)

        # 3. Isolation Forest 异常评分
        ax = axes[0, 2]
        ax.scatter(range(len(data)), data['iso_score'], c=data['iso_pred'],
                   cmap='RdYlGn_r', alpha=0.6, s=15)
        ax.axhline(np.percentile(data['iso_score'], 5), color='red', linestyle='--', alpha=0.5)
        ax.set_xlabel('电池序号')
        ax.set_ylabel('异常评分')
        ax.set_title('Isolation Forest 异常评分')
        ax.grid(True, alpha=0.3)

        # 4. 散点图 (K值 vs 第一个特征)
        if len(self.feature_cols) > 0:
            ax = axes[1, 0]
            fc = self.feature_cols[0]
            colors = ['red' if a else 'steelblue' for a in data['ensemble_anomaly']]
            ax.scatter(data[fc], data[k_col], c=colors, alpha=0.6, s=20)
            ax.set_xlabel(fc)
            ax.set_ylabel('K值')
            ax.set_title(f'K值 vs {fc}')
            ax.grid(True, alpha=0.3)

        # 5. 异常分数分布
        ax = axes[1, 1]
        norm = data['ensemble_score']
        ax.hist(norm, bins=40, alpha=0.7, color='coral', edgecolor='white')
        ax.axvline(np.percentile(norm, 95), color='red', linestyle='--',
                   label=f'P95={np.percentile(norm, 95):.2f}')
        ax.set_xlabel('综合异常分数')
        ax.set_ylabel('频数')
        ax.set_title('综合异常分数分布')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

        # 6. 分级建议
        ax = axes[1, 2]
        k = data[k_col].values
        thresholds = self.results.get('thresholds', {})
        rec = thresholds.get('recommended_k_max', np.percentile(k, 95))

        ax.hist(k, bins=50, alpha=0.7, color='lightgreen', edgecolor='white')
        ax.axvline(rec, color='red', linewidth=2, label=f'推荐上限={rec:.4f}')
        ax.axvline(np.percentile(k, 50), color='blue', linestyle='--', label=f'中位数={np.median(k):.4f}')
        ax.set_xlabel('K值')
        ax.set_ylabel('频数')
        ax.set_title('分选阈值建议')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"  📊 分析图保存至: {save_path}")
        plt.close()


def run_demo():
    """演示模式: 生成模拟电池数据并分析"""
    print("=" * 60)
    print("  K值离散分析与异常检测 — 演示模式")
    print("=" * 60)

    np.random.seed(42)
    n = 1000

    # 模拟正常电池 K值 ~ 0.5-1.5%/day
    k_normal = np.random.normal(1.0, 0.25, n)

    # 插入异常: 高K值电池 (自放电异常)
    n_anomalies = 30
    k_high = np.random.uniform(2.5, 5.0, n_anomalies)

    # 插入低K值电池 (可能测量异常)
    k_low = np.random.uniform(-1.0, -0.2, 10)

    k_values = np.concatenate([k_normal, k_high, k_low])
    np.random.shuffle(k_values)

    # 模拟其他特征
    ocv = 3.7 + np.random.normal(0, 0.02, len(k_values))  # 开路电压
    acr = 15 + np.random.normal(0, 2, len(k_values))       # 交流内阻
    capacity = 2000 + np.random.normal(0, 30, len(k_values)) + k_values * 10  # 容量

    df = pd.DataFrame({
        "battery_id": [f"BAT-{i:05d}" for i in range(len(k_values))],
        "k_value": k_values,
        "ocv_V": ocv,
        "acr_mOhm": acr,
        "capacity_mAh": capacity,
        "voltage_drop_mV": np.abs(k_values) * 24 + np.random.normal(0, 2, len(k_values))
    })

    print(f"\n📊 模拟数据: {len(df)} 条电池 (含 {n_anomalies+10} 个异常)")
    print(f"  K值范围: [{k_values.min():.3f}, {k_values.max():.3f}]")

    detector = KValueAnomalyDetector(contamination=0.05)
    detector.analyze(df, k_col="k_value",
                     feature_cols=["ocv_V", "acr_mOhm", "capacity_mAh", "voltage_drop_mV"])

    # 保存结果
    out_path = "D:/hermes/hermes-data/profiles/mybot/knowledge_base/reference/algorithm-research/k_value_anomaly_demo.json"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(detector.results, f, indent=2, ensure_ascii=False)
    print(f"\n📄 结果已保存至: {out_path}")

    plot_path = "D:/hermes/hermes-data/profiles/mybot/knowledge_base/reference/algorithm-research/k_value_analysis.png"
    detector.plot_results(save_path=plot_path)

    return detector.results


def run_from_csv(csv_path: str, k_col: str, feature_cols: list = None):
    """从CSV加载真实数据并分析"""
    df = pd.read_csv(csv_path)
    print(f"📊 加载数据: {len(df)} 条, 列: {list(df.columns)}")

    detector = KValueAnomalyDetector(contamination=0.05)
    detector.analyze(df, k_col=k_col, feature_cols=feature_cols)

    out_dir = Path(csv_path).parent
    json_path = out_dir / f"k_value_analysis_{Path(csv_path).stem}.json"
    with open(json_path, 'w') as f:
        json.dump(detector.results, f, indent=2, ensure_ascii=False)
    print(f"\n📄 结果已保存至: {json_path}")

    plot_path = out_dir / f"k_value_analysis_{Path(csv_path).stem}.png"
    detector.plot_results(save_path=str(plot_path))

    return detector.results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="K值离散分析 + 异常检测")
    parser.add_argument("--demo", action="store_true", help="演示模式")
    parser.add_argument("--data", help="CSV数据文件路径")
    parser.add_argument("--k-col", default="k_value", help="K值列名")
    parser.add_argument("--features", help="特征列名,逗号分隔")

    args = parser.parse_args()

    if args.demo:
        run_demo()
    elif args.data:
        features = args.features.split(',') if args.features else None
        run_from_csv(args.data, args.k_col, features)
    else:
        parser.print_help()
        print("\n示例:")
        print("  python k_value_anomaly_detector.py --demo")
        print("  python k_value_anomaly_detector.py --data battery_data.csv --k-col k_value")
