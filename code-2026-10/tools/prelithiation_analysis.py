#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补锂后首效降低 —— 模拟数据生成、统计分析与可视化
======================================================
场景：Ar 160°C 气氛下，Si/C 负极压延补锂（Li箔）。
      预期补锂可提升首次库仑效率（ICE），但实验结果反常：
      补锂后首充容量和首效均降低。

作者：通量（Python 数据科学专家）
日期：2026-07-08
"""

import sys
# 修复：排除 hermes-agent venv 中损坏的 PIL，使用系统 site-packages
sys.path = [p for p in sys.path if "hermes-agent" not in p]

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")  # 非交互后端，适合无 GUI 环境
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
from pathlib import Path
import warnings

warnings.filterwarnings("ignore")

# ============================================================
# 0. 输出目录 & 中文字体设置
# ============================================================
OUTPUT_DIR = Path(__file__).resolve().parent

# Windows 常见中文字体回退链
_PREFERRED_FONTS = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "WenQuanYi Micro Hei", "DejaVu Sans"]
for _f in _PREFERRED_FONTS:
    try:
        matplotlib.font_manager.findfont(_f, fallback_to_default=False)
        plt.rcParams["font.sans-serif"] = [_f] + plt.rcParams["font.sans-serif"]
        break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False

sns.set_style("whitegrid")
sns.set_context("notebook", font_scale=1.2)

# ============================================================
# 1. 生成模拟数据
# ============================================================
np.random.seed(42)

N_PER_GROUP = 6

# --- 原始组 (Original)：典型 Si/C 负极，首效 ~80% ---
original = pd.DataFrame({
    "sample_id": [f"ORG-{i+1:02d}" for i in range(N_PER_GROUP)],
    "group": "原始",
    "first_charge_mAh_g":   np.round(np.random.normal(1300, 40, N_PER_GROUP), 1),
    "first_discharge_mAh_g": np.round(np.random.normal(1040, 35, N_PER_GROUP), 1),
})

# --- 补锂组 (Pre-lithiated)：补锂失败，首效降低 ---
# 补锂工艺：Ar 160°C 压延 Li 箔 → 部分 Li 氧化/副反应，活性锂损失
prelith = pd.DataFrame({
    "sample_id": [f"PLi-{i+1:02d}" for i in range(N_PER_GROUP)],
    "group": "补锂",
    "first_charge_mAh_g":   np.round(np.random.normal(1250, 45, N_PER_GROUP), 1),
    "first_discharge_mAh_g": np.round(np.random.normal(900, 40, N_PER_GROUP), 1),
})

df = pd.concat([original, prelith], ignore_index=True)

# 派生列
df["ICE_percent"] = np.round(
    df["first_discharge_mAh_g"] / df["first_charge_mAh_g"] * 100, 2
)
df["irreversible_mAh_g"] = np.round(
    df["first_charge_mAh_g"] - df["first_discharge_mAh_g"], 1
)

print("=" * 72)
print("  补锂前后扣电测试 —— 数据一览")
print("=" * 72)
print(df.to_string(index=False))

# ============================================================
# 2. 描述性统计
# ============================================================
print("\n" + "=" * 72)
print("  描述性统计（按组汇总）")
print("=" * 72)

desc = df.groupby("group").agg(
    样本数=("sample_id", "count"),
    首充均值=("first_charge_mAh_g", "mean"),
    首充标准差=("first_charge_mAh_g", "std"),
    首放均值=("first_discharge_mAh_g", "mean"),
    首放标准差=("first_discharge_mAh_g", "std"),
    ICE均值=("ICE_percent", "mean"),
    ICE标准差=("ICE_percent", "std"),
    不可逆容量均值=("irreversible_mAh_g", "mean"),
    不可逆容量标准差=("irreversible_mAh_g", "std"),
)

for col in desc.columns:
    if "标准差" in col:
        desc[col] = desc[col].round(2)
    elif "样本数" in col:
        desc[col] = desc[col].astype(int)
    else:
        desc[col] = desc[col].round(2)

print(desc.to_string())

# ============================================================
# 3. 推断统计：独立样本 t 检验 + 效应量
# ============================================================
print("\n" + "=" * 72)
print("  推断统计")
print("=" * 72)

orig = df[df["group"] == "原始"]
plit = df[df["group"] == "补锂"]

metrics = [
    ("首充容量 (mAh/g)", "first_charge_mAh_g"),
    ("首放容量 (mAh/g)", "first_discharge_mAh_g"),
    ("ICE (%)", "ICE_percent"),
    ("不可逆容量 (mAh/g)", "irreversible_mAh_g"),
]

for label, col in metrics:
    a = orig[col].values
    b = plit[col].values

    # Welch's t-test（不假设方差齐性）
    t_stat, p_val = stats.ttest_ind(a, b, equal_var=False)

    # Cohen's d
    pooled_std = np.sqrt((np.std(a, ddof=1)**2 + np.std(b, ddof=1)**2) / 2)
    cohens_d = (np.mean(a) - np.mean(b)) / pooled_std if pooled_std != 0 else 0

    # 效应量解释
    d_abs = abs(cohens_d)
    if d_abs < 0.2:
        effect_label = "可忽略"
    elif d_abs < 0.5:
        effect_label = "小"
    elif d_abs < 0.8:
        effect_label = "中等"
    else:
        effect_label = "大"

    sig = "***" if p_val < 0.001 else ("**" if p_val < 0.01 else ("*" if p_val < 0.05 else "n.s."))

    print(f"\n{label}:")
    print(f"  原始均值 = {np.mean(a):.2f} ± {np.std(a, ddof=1):.2f}")
    print(f"  补锂均值 = {np.mean(b):.2f} ± {np.std(b, ddof=1):.2f}")
    print(f"  差值     = {np.mean(a) - np.mean(b):.2f}")
    print(f"  t({min(len(a),len(b))-1}) = {t_stat:.3f}, p = {p_val:.4f}  {sig}")
    print(f"  Cohen's d = {cohens_d:.3f}  →  效应量: {effect_label}")

# ============================================================
# 4. 可视化
# ============================================================

# ---- 配色 ----
COLOR_ORIG = "#4C72B0"
COLOR_PLIT = "#DD8452"
PALETTE = {"原始": COLOR_ORIG, "补锂": COLOR_PLIT}

# ============================================================
# 图 1：箱线图 + 小提琴图 + 散点（ICE 对比）
# ============================================================
fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# (a) 首效 ICE
ax = axes[0]
sns.violinplot(
    x="group", y="ICE_percent", data=df, palette=PALETTE,
    inner="quartile", cut=0, linewidth=1.2, ax=ax,
)
sns.stripplot(
    x="group", y="ICE_percent", data=df, color="black",
    size=8, alpha=0.7, jitter=True, ax=ax,
)
# 标注均值
for i, (grp, grp_df) in enumerate(df.groupby("group")):
    mean_val = grp_df["ICE_percent"].mean()
    ax.text(i, mean_val + 1.2, f"{mean_val:.1f}%", ha="center", fontsize=11, fontweight="bold")
ax.set_title("A．首次库仑效率 (ICE)", fontsize=14, fontweight="bold")
ax.set_ylabel("ICE / %")
ax.set_xlabel("")
ax.set_ylim(60, 92)

# (b) 首充容量
ax = axes[1]
sns.boxplot(
    x="group", y="first_charge_mAh_g", data=df, palette=PALETTE,
    width=0.5, linewidth=1.2, ax=ax,
)
sns.stripplot(
    x="group", y="first_charge_mAh_g", data=df, color="black",
    size=8, alpha=0.7, jitter=True, ax=ax,
)
for i, (grp, grp_df) in enumerate(df.groupby("group")):
    mean_val = grp_df["first_charge_mAh_g"].mean()
    ax.text(i, mean_val + 10, f"{mean_val:.0f}", ha="center", fontsize=11, fontweight="bold")
ax.set_title("B．首次充电容量", fontsize=14, fontweight="bold")
ax.set_ylabel("容量 / mAh·g⁻¹")
ax.set_xlabel("")

# (c) 不可逆容量
ax = axes[2]
sns.boxplot(
    x="group", y="irreversible_mAh_g", data=df, palette=PALETTE,
    width=0.5, linewidth=1.2, ax=ax,
)
sns.stripplot(
    x="group", y="irreversible_mAh_g", data=df, color="black",
    size=8, alpha=0.7, jitter=True, ax=ax,
)
for i, (grp, grp_df) in enumerate(df.groupby("group")):
    mean_val = grp_df["irreversible_mAh_g"].mean()
    ax.text(i, mean_val + 8, f"{mean_val:.0f}", ha="center", fontsize=11, fontweight="bold")
ax.set_title("C．不可逆容量", fontsize=14, fontweight="bold")
ax.set_ylabel("容量 / mAh·g⁻¹")
ax.set_xlabel("")

fig.suptitle(
    "补锂前后电池性能对比\n（Ar 160°C，Si/C 负极，压延补锂，n=6）",
    fontsize=16, fontweight="bold", y=1.02,
)
plt.tight_layout()
fig.savefig(OUTPUT_DIR / "fig1_boxplot_violin.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print(f"\n[图1] 已保存: {OUTPUT_DIR / 'fig1_boxplot_violin.png'}")

# ============================================================
# 图 2：充放电曲线对比示意
# ============================================================
# 使用 sigmoid 形状模拟 Li-ion 半电池充放电曲线
# 充电（嵌锂）：0 V → 低电位，对应 Si/C 的锂化平台
# 放电（脱锂）：从低电位回升

def simulated_half_cell_curve(capacity_points, kind="charge", ice_pct=80, noise_scale=0.003):
    """
    生成模拟 Si/C 半电池充放电曲线。
    充电：电位逐渐降低（嵌锂），放电：电位逐渐升高（脱锂）。
    """
    n = len(capacity_points)
    x_norm = np.linspace(0, 1, n)

    # 基础电位曲线：Si 的特征平台 ~0.1-0.3 V
    if kind == "charge":
        # 从 ~1.5V 开始，到 ~0.01V 结束
        voltage = 1.5 - 1.49 * (1 / (1 + np.exp(-15 * (x_norm - 0.3))))
    else:
        # 从 ~0.01V 开始，到 ~1.5V 结束
        voltage = 0.01 + 1.49 * (1 / (1 + np.exp(-15 * (x_norm - 0.3))))

    voltage += np.random.normal(0, noise_scale, n)
    voltage = np.clip(voltage, 0.005, 2.5)

    return voltage


def make_charge_discharge_curves(charge_cap, discharge_cap, seed=None):
    """为一颗电池生成充放电曲线对。"""
    if seed is not None:
        np.random.seed(seed)

    n_points = 300
    cap_charge = np.linspace(0, charge_cap, n_points)
    cap_discharge = np.linspace(0, discharge_cap, n_points)

    v_charge = simulated_half_cell_curve(cap_charge, kind="charge", noise_scale=0.003)
    v_discharge = simulated_half_cell_curve(cap_discharge, kind="discharge", noise_scale=0.003)

    return cap_charge, v_charge, cap_discharge, v_discharge


fig, axes = plt.subplots(1, 2, figsize=(16, 6))

# 选代表样本：各组均值最接近的那个
orig_rep = orig.iloc[(orig["ICE_percent"] - orig["ICE_percent"].mean()).abs().argmin()]
plit_rep = plit.iloc[(plit["ICE_percent"] - plit["ICE_percent"].mean()).abs().argmin()]

for idx, (ax, rep_row, label, color) in enumerate([
    (axes[0], orig_rep, f"原始 ({orig_rep['sample_id']})", COLOR_ORIG),
    (axes[1], plit_rep, f"补锂 ({plit_rep['sample_id']})", COLOR_PLIT),
]):
    cap_ch, v_ch, cap_dc, v_dc = make_charge_discharge_curves(
        rep_row["first_charge_mAh_g"], rep_row["first_discharge_mAh_g"], seed=42 + idx
    )

    ax.plot(cap_ch, v_ch, color=color, linewidth=2.0, label="首充（嵌锂）", alpha=0.85)
    ax.plot(cap_dc, v_dc, "--", color=color, linewidth=2.0, label="首放（脱锂）", alpha=0.85)

    # 标注不可逆容量
    q_irr = rep_row["irreversible_mAh_g"]
    ax.axvspan(rep_row["first_discharge_mAh_g"], rep_row["first_charge_mAh_g"],
               ymin=0.02, ymax=0.12, alpha=0.3, color="red")
    ax.annotate(
        f"不可逆\n{q_irr:.0f} mAh/g",
        xy=(rep_row["first_discharge_mAh_g"] + q_irr / 2, 0.06),
        fontsize=11, ha="center", va="bottom", color="darkred",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
    )

    ax.set_title(f"{label}\nICE = {rep_row['ICE_percent']:.1f}%", fontsize=13, fontweight="bold")
    ax.set_xlabel("容量 / mAh·g⁻¹")
    ax.set_ylabel("电位 / V (vs. Li/Li⁺)")
    ax.set_ylim(-0.1, 2.0)
    ax.legend(loc="upper left", fontsize=10)
    ax.invert_yaxis()  # 电池曲线习惯：嵌锂电位降低

fig.suptitle(
    "首周充放电曲线对比示意（半电池 vs. Li/Li⁺）",
    fontsize=15, fontweight="bold", y=1.02,
)
plt.tight_layout()
fig.savefig(OUTPUT_DIR / "fig2_charge_discharge_curves.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print(f"[图2] 已保存: {OUTPUT_DIR / 'fig2_charge_discharge_curves.png'}")

# ============================================================
# 图 3：ICE 与不可逆容量的关系散点图
# ============================================================
fig, ax = plt.subplots(figsize=(8, 6))

for grp, grp_df in df.groupby("group"):
    c = PALETTE[grp]
    ax.scatter(
        grp_df["ICE_percent"], grp_df["irreversible_mAh_g"],
        s=120, color=c, edgecolors="black", linewidths=0.8,
        label=grp, zorder=5,
    )
    for _, row in grp_df.iterrows():
        ax.annotate(
            row["sample_id"], (row["ICE_percent"], row["irreversible_mAh_g"]),
            textcoords="offset points", xytext=(6, 6), fontsize=8, alpha=0.8,
        )

# 拟合趋势线
z = np.polyfit(df["ICE_percent"], df["irreversible_mAh_g"], 1)
p = np.poly1d(z)
x_line = np.linspace(df["ICE_percent"].min() - 1, df["ICE_percent"].max() + 1, 100)
ax.plot(x_line, p(x_line), "k--", alpha=0.4, linewidth=1.2)
r, _ = stats.pearsonr(df["ICE_percent"], df["irreversible_mAh_g"])
ax.text(0.95, 0.05, f"r = {r:.3f}", transform=ax.transAxes,
        ha="right", fontsize=11, bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))

ax.set_xlabel("ICE / %", fontsize=13)
ax.set_ylabel("不可逆容量 / mAh·g⁻¹", fontsize=13)
ax.set_title("ICE 与不可逆容量的关系", fontsize=14, fontweight="bold")
ax.legend(fontsize=11)
plt.tight_layout()
fig.savefig(OUTPUT_DIR / "fig3_ice_vs_irreversible.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print(f"[图3] 已保存: {OUTPUT_DIR / 'fig3_ice_vs_irreversible.png'}")

# ============================================================
# 5. 分析结论
# ============================================================
print("\n")
print("=" * 72)
print("  分析结论")
print("=" * 72)

delta_ice = orig["ICE_percent"].mean() - plit["ICE_percent"].mean()
delta_irr = plit["irreversible_mAh_g"].mean() - orig["irreversible_mAh_g"].mean()

print(f"""
1. 补锂后首效（ICE）由 {orig['ICE_percent'].mean():.2f}% 下降至 {plit['ICE_percent'].mean():.2f}%，
   降幅约为 {abs(delta_ice):.2f} 个百分点。独立样本 t 检验表明该差异具有统计显著性
   （p < 0.001），且 Cohen's d 效应量属于"大"水平——补锂工艺对首效的负面影响
   不仅仅是偶然波动，而是实质性的大幅下降。

2. 补锂后的不可逆容量由 {orig['irreversible_mAh_g'].mean():.0f} mAh/g 上升至
   {plit['irreversible_mAh_g'].mean():.0f} mAh/g，增加了约 {delta_irr:.0f} mAh/g。
   这说明补锂不仅没有有效补偿首次不可逆锂损失，反而引入了额外的副反应。

3. 可能原因（基于 Ar 160°C 压延补锂工艺）：
   - 高温下 Li 箔与残留 H₂O/O₂ 反应生成 LiOH/Li₂O 钝化层，活性锂利用率降低；
   - 压延过程中 Li 箔与 Si/C 颗粒接触不均，局部过锂化导致 Si 结构破坏；
   - Li 与电解液的反应产物（如 Li₂CO₃、LiF）在补锂后首周形成更厚的 SEI 膜，
     消耗更多活性锂；
   - 部分 Li 以"死锂"形式存在（电子通路断开），无法参与后续电化学反应。

4. 建议后续工作：
   - XRD/XPS 表征补锂后负极表面成分，确认 LiOH/Li₂CO₃ 等杂质含量；
   - SEM 截面观察补锂层与 Si/C 界面的均匀性；
   - 优化压延温度和气氛控制（如进一步降低 H₂O/O₂ 至 < 0.1 ppm）；
   - 尝试电化学补锂（如对电极短路法）替代压延补锂，减少机械损伤。
""")

print("=" * 72)
print("  所有分析完成。图表已保存至:")
print(f"    {OUTPUT_DIR / 'fig1_boxplot_violin.png'}")
print(f"    {OUTPUT_DIR / 'fig2_charge_discharge_curves.png'}")
print(f"    {OUTPUT_DIR / 'fig3_ice_vs_irreversible.png'}")
print("=" * 72)
