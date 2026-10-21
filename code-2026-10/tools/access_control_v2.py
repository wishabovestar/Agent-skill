#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
门禁考勤数据自动化处理系统 v2.0
==================================
完整交互式闭环：输入(Input)→筛选(Filter)→处理(Process)→检查(Check)→导出(Export)

基于用户2张微信截图真实需求构建:
  图片1: Excel公式处理流程截图
  图片2: Python自动化需求描述

工作时段定义:
  - 上午: 09:00 ~ 11:50
  - 下午: 13:30 ~ 18:20
异常阈值:
  - 检查窗口: 15min~240min（此范围内的记录才检查进出方向配对）
  - <15min: 短暂进出（忽略，不纳入异常判断）
  - >240min: 可能全天班（忽略，不纳入异常判断）
  - 窗口内进出方向不配对（进→进 或 出→出）→ 标记"异常(未配对)"
  - 窗口内进出方向配对（进→出 或 出→进）→ 标记"正常"

使用方式:
  python access_control_v2.py                # 交互模式（推荐）
  python access_control_v2.py data.xlsx       # 一键模式
  python access_control_v2.py data.xlsx --all # 全自动模式

交互流程: load → [check] → filter → [check] → process → [check] → export
"""

import sys
import os
import re
import json
from pathlib import Path
from datetime import datetime, time, timedelta
from typing import Optional, List, Tuple
import warnings
warnings.filterwarnings("ignore")

# ── 依赖检查 ──────────────────────────────────────────────────
DEP_OK = True
try:
    import pandas as pd
    import numpy as np
except ImportError:
    DEP_OK = False
    
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    try:
        plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
    except:
        pass
    MATPLOTLIB_OK = True
except ImportError:
    MATPLOTLIB_OK = False

# ── 全局配置 ──────────────────────────────────────────────────
MORNING_START = time(9, 0, 0)
MORNING_END = time(11, 50, 0)
AFTERNOON_START = time(13, 30, 0)
AFTERNOON_END = time(18, 20, 0)
# 异常检查窗口（非阈值）—— 仅在15~240min范围内检查进出方向配对
# <15min=短暂进出忽略, >240min=全天班忽略
ANOMALY_WINDOW_MIN = 15
ANOMALY_WINDOW_MAX = 240

# 站点列表
SITES = ["珠海", "重庆", "马来西亚"]

VERSION = "2.0.0"


# ══════════════════════════════════════════════════════════════════
# 模块1：输入 (Input / Load)
# ══════════════════════════════════════════════════════════════════

def load_data(filepath: str) -> pd.DataFrame:
    """Step 1: 加载原始数据"""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"❌ 文件不存在: {filepath}")
    
    ext = path.suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(filepath, encoding="utf-8-sig")
    elif ext in (".xlsx", ".xls"):
        engine = "openpyxl" if ext == ".xlsx" else "xlrd"
        df = pd.read_excel(filepath, engine=engine)
    else:
        raise ValueError(f"不支持格式: {ext}，请使用 .xlsx / .xls / .csv")
    
    return df


def inspect_columns(df: pd.DataFrame) -> dict:
    """自动检测列结构，返回列映射"""
    col_map = {"time_col": None, "date_col": None, "name_col": None,
               "direction_col": None, "device_col": None, "site_col": None}
    
    for col in df.columns:
        c = str(col).lower()
        if any(k in c for k in ["时间", "time", "时刻", "时分"]):
            col_map["time_col"] = col
        elif any(k in c for k in ["日期", "date", "日", "年月日"]):
            col_map["date_col"] = col
        elif any(k in c for k in ["姓名", "工号", "name", "人员", "员工", "id"]):
            col_map["name_col"] = col
        elif any(k in c for k in ["进出", "方向", "进/出", "出入"]):
            col_map["direction_col"] = col
        elif any(k in c for k in ["设备", "device", "编号", "gate", "闸"]):
            col_map["device_col"] = col
        elif any(k in c for k in ["站点", "site", "地点", "区域", "office", "位置"]):
            col_map["site_col"] = col
    
    return col_map


def load_step(filepath: str):
    """加载+检查环节"""
    print(f"\n{'─'*50}")
    print("  [输入] 步骤1：加载数据")
    print(f"{'─'*50}")
    
    df = load_data(filepath)
    col_map = inspect_columns(df)
    
    print(f"\n  ✓ 已加载: {len(df)} 行 × {len(df.columns)} 列")
    print(f"  ✓ 来源文件: {Path(filepath).name}")
    
    # 展示列识别结果
    print(f"\n  ┌─ 列结构识别结果:")
    for key, label in [("date_col", "日期列"), ("time_col", "时间列"),
                       ("name_col", "姓名/工号"), ("direction_col", "进出方向"),
                       ("device_col", "设备编号"), ("site_col", "站点")]:
        val = col_map.get(key)
        if val:
            print(f"  │  ✓ {label}: [{val}]")
        else:
            print(f"  │  ○ {label}: 未识别到（后续可手动指定）")
    print(f"  └─")
    
    return df, col_map


# ══════════════════════════════════════════════════════════════════
# 模块2：筛选 (Filter / Search)
# ══════════════════════════════════════════════════════════════════

def filter_by_site(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    """按站点筛选"""
    site_col = col_map.get("site_col")
    if not site_col:
        print("  ○ 未识别到站点列，跳过站点筛选")
        return df
    
    sites_available = df[site_col].dropna().unique()
    print(f"\n  ┌─ 站点筛选:")
    for i, s in enumerate(sites_available, 1):
        cnt = len(df[df[site_col] == s])
        print(f"  │  {i}. {s} ({cnt}条)")
    
    sel = input("  │  选择编号（留空=全部, 多选逗号分隔）: ").strip()
    if sel:
        selected = []
        for c in sel.split(","):
            c = c.strip()
            if c.isdigit() and 1 <= int(c) <= len(sites_available):
                selected.append(sites_available[int(c) - 1])
        if selected:
            df = df[df[site_col].isin(selected)]
            print(f"  │  → 筛选后: {len(df)} 行")
    print(f"  └─")
    return df


def filter_by_person(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    """按人员关键词/工号筛选"""
    name_col = col_map.get("name_col")
    if not name_col:
        return df
    
    kw = input(f"  人员关键词/工号（留空=全部, 排除用前加-: -张三）: ").strip()
    if not kw:
        return df
    
    # 排除模式
    if kw.startswith("-"):
        exclude_kw = kw[1:]
        before = len(df)
        df = df[~df[name_col].astype(str).str.contains(exclude_kw, na=False)]
        print(f"  → 排除'{exclude_kw}': {before}→{len(df)}行")
    else:
        before = len(df)
        df = df[df[name_col].astype(str).str.contains(kw, na=False)]
        print(f"  → 筛选'{kw}': {before}→{len(df)}行")
    
    return df


def filter_by_date(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    """按日期范围筛选"""
    date_col = col_map.get("date_col")
    if not date_col:
        # 如果时间列中有日期信息也可以
        time_col = col_map.get("time_col")
        if time_col:
            df[time_col] = pd.to_datetime(df[time_col])
            date_col = time_col
        else:
            return df
    
    date_range = input("  日期范围（格式: 2026-01-01~2026-01-31，留空=全部）: ").strip()
    if not date_range or "~" not in date_range:
        return df
    
    try:
        start_str, end_str = date_range.split("~")
        start = pd.to_datetime(start_str.strip())
        end = pd.to_datetime(end_str.strip())
        
        if date_col not in df.columns:
            # 从时间列提取日期
            if col_map.get("time_col") and date_col != col_map.get("time_col"):
                df["_日期"] = pd.to_datetime(df[col_map["time_col"]]).dt.date
                date_col = "_日期"
                start = start.date()
                end = end.date()
        
        if date_col in df.columns:
            before = len(df)
            df[date_col] = pd.to_datetime(df[date_col])
            mask = (df[date_col] >= start) & (df[date_col] <= end)
            df = df[mask]
            print(f"  → 日期范围筛选: {before}→{len(df)}行")
    except Exception as e:
        print(f"  ⚠ 日期解析错误: {e}")
    
    return df


def filter_step(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    """完整筛选环节"""
    print(f"\n{'─'*50}")
    print("  [筛选] 步骤2：数据筛选")
    print(f"{'─'*50}")
    print(f"  当前数据: {len(df)} 行")
    
    df = filter_by_site(df, col_map)
    df = filter_by_person(df, col_map)
    df = filter_by_date(df, col_map)
    
    return df


def check_step(label: str, df: pd.DataFrame, details: str = "") -> bool:
    """检查环节（通用）"""
    print(f"\n{'─'*40}")
    print(f"  [检查] {label} — 当前数据: {len(df)} 行")
    if details:
        print(f"  {details}")
    print(f"{'─'*40}")
    
    ans = input("  确认继续? (Y/n): ").strip().lower()
    return ans != "n"


# ══════════════════════════════════════════════════════════════════
# 模块3：功能调用 (Process / Function Call)
# ══════════════════════════════════════════════════════════════════

def classify_work_period(dt_val) -> str:
    """F1: 工作时段分类（对应原Excel K列）"""
    if pd.isna(dt_val):
        return "未知"
    try:
        t = dt_val.time() if hasattr(dt_val, 'time') else dt_val
    except:
        return "未知"
    
    if MORNING_START <= t <= MORNING_END:
        return "上午工作时段"
    elif AFTERNOON_START <= t <= AFTERNOON_END:
        return "下午工作时段"
    else:
        return "非工作时段"


def calc_timespan_series(df: pd.DataFrame, time_col: str, group_col: str = None) -> pd.Series:
    """F2: 时间跨度计算（对应原Excel M列公式）"""
    if time_col not in df.columns:
        return pd.Series(0, index=df.index)
    
    if group_col and group_col in df.columns:
        spans = df.groupby(group_col)[time_col].diff().dt.total_seconds() / 60
    else:
        spans = df[time_col].diff().dt.total_seconds() / 60
    
    return spans.fillna(0).round(1)


def detect_anomaly(timespan_min: float, current_dir: str = None, prev_dir: str = None) -> str:
    """F3: 异常检测（对应原Excel O列公式）
    
    公式逻辑: O2=IF(AND(M2>15,M2<240),IF(G2=判断条件,"异常",""),"")
    - 时间跨度在15~240min之间的记录才检查（检查窗口，非异常阈值）
    - 15min以下: 短暂进出(拿快递/抽烟等)，忽略
    - 240min以上: 可能全天/半天班，忽略
    - 窗口内检查进出方向是否配对 → 不配对=异常
    """
    if timespan_min == 0:
        return ""  # 首条记录，无前一条可比
    
    # 时间跨度超出检查窗口 → 不纳入异常判断
    if timespan_min < ANOMALY_WINDOW_MIN or timespan_min > ANOMALY_WINDOW_MAX:
        return ""
    
    # 在检查窗口(15~240min)内 → 检查进出方向是否配对
    if current_dir and prev_dir and current_dir == prev_dir:
        # 连续两次同一方向（进→进 或 出→出）= 缺少配对记录
        return "异常(未配对)"
    
    return "正常"


def classify_entry_detail(period: str, timespan: float, anomaly: str, direction: str = "") -> str:
    """F4: 进出详情分类（对应原Excel N列CHOOSE逻辑）"""
    if pd.isna(timespan) or timespan == 0:
        return "首次记录"
    if anomaly:
        return f"{anomaly}({timespan:.0f}min,{direction})"
    elif "非工作" in period:
        return f"非工作时段进出({timespan:.0f}min)"
    else:
        return f"{period}正常进出({timespan:.0f}min,{direction})"


def calc_timeliness(df: pd.DataFrame) -> dict:
    """F5: 统计及时率"""
    total = len(df)
    if total == 0:
        return {"total": 0, "normal": 0, "anomaly": 0, "rate": 0.0}
    
    anomaly_count = len(df[df["是否超时"].str.contains("异常", na=False)])
    normal_count = total - anomaly_count
    rate = round(normal_count / total * 100, 2)
    
    # 按站点分组统计
    site_stats = {}
    if "区域" in df.columns:
        for site in df["区域"].unique():
            site_df = df[df["区域"] == site]
            site_anomaly = len(site_df[site_df["是否超时"].str.contains("异常", na=False)])
            site_stats[site] = {
                "total": len(site_df), "normal": len(site_df) - site_anomaly,
                "anomaly": site_anomaly,
                "rate": round((len(site_df) - site_anomaly) / len(site_df) * 100, 2)
            }
    
    return {
        "total": total, "normal": normal_count, "anomaly": anomaly_count,
        "rate": rate, "site_stats": site_stats,
    }


def generate_summary(stats: dict, site: str = "") -> List[str]:
    """F6: 生成文字总结（1~3行）"""
    lines = []
    prefix = f"[{site}] " if site else ""
    
    lines.append(f"{prefix}共{stats['total']}条记录，正常{stats['normal']}条，"
                  f"异常{stats['anomaly']}条，及时率{stats['rate']}%")
    
    if stats['anomaly'] > 0:
        ratio = stats['anomaly'] / stats['total'] * 100 if stats['total'] > 0 else 0
        lines.append(f"{prefix}需关注异常占比{ratio:.1f}%")
    
    if stats['rate'] >= 95:
        lines.append(f"{prefix}整体运行良好")
    elif stats['rate'] >= 80:
        lines.append(f"{prefix}及时率尚可，仍有优化空间")
    else:
        lines.append(f"{prefix}及时率偏低，建议排查")
    
    return lines[:3]  # 确保不超过3行


def visualize(df: pd.DataFrame, output_path: str = "access_analysis.png"):
    """F7: 可视化"""
    if not MATPLOTLIB_OK:
        print("  ⚠ matplotlib不可用，跳过图表生成")
        return
    
    n_cols = 0
    if "区域" in df.columns: n_cols += 1
    if "时间跨度/min" in df.columns: n_cols += 1
    if "工作时段" in df.columns: n_cols += 1
    if "是否超时" in df.columns: n_cols += 1
    n_cols = max(n_cols, 1)
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("门禁考勤数据分析报告", fontsize=14, fontweight='bold')
    
    ax_idx = 0
    # 1. 站点分布
    if "区域" in df.columns:
        site_counts = df["区域"].value_counts()
        axes[0, 0].bar(site_counts.index, site_counts.values, color='steelblue')
        axes[0, 0].set_title("各站点记录数")
        axes[0, 0].tick_params(axis='x', rotation=45)
        ax_idx += 1
    
    # 2. 时间跨度分布
    if "时间跨度/min" in df.columns:
        spans = df["时间跨度/min"].dropna()
        spans = spans[spans.between(0, 500)]  # 排除极端值
        ax = axes[0, 1]
        ax.hist(spans, bins=30, color='coral', alpha=0.7, edgecolor='white')
        ax.axvline(x=ANOMALY_WINDOW_MIN, color='orange', linestyle='--', alpha=0.5, label=f'检查窗口{ANOMALY_WINDOW_MIN}min')
        ax.axvline(x=ANOMALY_WINDOW_MAX, color='orange', linestyle='--', alpha=0.5, label=f'检查窗口{ANOMALY_WINDOW_MAX}min')
        ax.set_title("时间跨度分布")
        ax.set_xlabel("时间跨度/min")
        ax.legend()
        ax_idx += 1
    
    # 3. 时段分布
    if "工作时段" in df.columns:
        period_counts = df["工作时段"].value_counts()
        axes[1, 0].pie(period_counts.values, labels=period_counts.index,
                       autopct='%1.1f%%', colors=['#66b3ff', '#ff9999', '#99ff99'])
        axes[1, 0].set_title("工作时段分布")
        ax_idx += 1
    
    # 4. 异常分布
    if "是否超时" in df.columns:
        anomaly_counts = df["是否超时"].value_counts()
        axes[1, 1].bar(anomaly_counts.index, anomaly_counts.values,
                       color=['#2ecc71', '#e74c3c', '#f39c12'])
        axes[1, 1].set_title("异常类型分布")
        axes[1, 1].tick_params(axis='x', rotation=45)
        ax_idx += 1
    
    # 隐藏未使用的子图
    for i in range(ax_idx, 4):
        r, c = divmod(i, 2)
        if r < 2 and c < 2:
            axes[r, c].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"  ✓ 图表已保存: {output_path}")
    plt.close()


# ══════════════════════════════════════════════════════════════════
# 模块4：处理流程 (完整Pipeline)
# ══════════════════════════════════════════════════════════════════

def process_step(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    """步骤3：执行完整业务处理"""
    print(f"\n{'─'*50}")
    print("  [处理] 步骤3：业务逻辑处理")
    print(f"{'─'*50}")
    
    result = df.copy()
    time_col = col_map.get("time_col")
    name_col = col_map.get("name_col")
    
    if not time_col:
        print("  ❌ 未识别到时间列，无法继续处理")
        return result
    
    # 确保时间列是datetime类型
    result[time_col] = pd.to_datetime(result[time_col])
    
    # 3a. 工作时段分类（K列）
    print("  3a. 工作时段分类...")
    result["工作时段"] = result[time_col].apply(classify_work_period)
    period_dist = result["工作时段"].value_counts().to_dict()
    for k, v in period_dist.items():
        print(f"      {k}: {v}条")
    
    # 3b. 时间跨度计算（M列）
    print("  3b. 时间跨度计算...")
    result["时间跨度/min"] = calc_timespan_series(result, time_col, name_col)
    print(f"      均值: {result['时间跨度/min'].mean():.1f} min | "
          f"中位数: {result['时间跨度/min'].median():.1f} min")
    
    # 3c. 异常检测（O列）—— 基于时间跨度窗口 + 进出方向配对
    print("  3c. 异常检测（检查窗口15~240min + 进出方向配对）...")
    # 前一条记录的进出方向，用于配对检测
    dir_col = col_map.get("direction_col")
    if dir_col and dir_col in result.columns:
        prev_dir = result[dir_col].shift(1)
        result["是否超时"] = result.apply(
            lambda r: detect_anomaly(r["时间跨度/min"], r.get(dir_col, ""), 
                                     prev_dir.get(r.name, "") 
                                     if hasattr(prev_dir, 'get') else ""),
            axis=1
        )
    else:
        result["是否超时"] = result["时间跨度/min"].apply(
            lambda x: detect_anomaly(x)
        )
    anomaly_dist = result["是否超时"].value_counts().to_dict()
    for k, v in anomaly_dist.items():
        if k:
            print(f"      {k}: {v}条")
    
    # 3d. 进出详情（N列）
    print("  3d. 进出详情分类...")
    dir_col = col_map.get("direction_col", "")
    result["进出详情"] = result.apply(
        lambda r: classify_entry_detail(
            r["工作时段"], r["时间跨度/min"], r["是否超时"],
            r.get(dir_col, "") if dir_col else ""
        ),
        axis=1
    )
    
    # 3e. L列标识
    result["标识"] = "2"
    print("  3e. L列标识: 已填充'2'")
    
    return result


# ══════════════════════════════════════════════════════════════════
# 模块5：检查 (Check / Verify)
# ══════════════════════════════════════════════════════════════════

def check_process(df: pd.DataFrame) -> bool:
    """处理后检查环节"""
    print(f"\n{'─'*40}")
    print("  [检查] 处理结果预览")
    print(f"{'─'*40}")
    
    print(f"\n  结果概览:")
    print(f"  ├─ 总行数: {len(df)}")
    
    required_cols = ["工作时段", "时间跨度/min", "是否超时", "进出详情", "标识"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        print(f"  ├─ ❌ 缺少列: {missing}")
        return False
    else:
        print(f"  ├─ ✓ 所有计算列已生成")
    
    # 预览前5行
    print(f"\n  数据预览（前5行）:")
    preview_cols = [c for c in ["区域", col_map.get("name_col",""), col_map.get("time_col",""),
                                 "工作时段", "时间跨度/min", "是否超时", "进出详情"]
                    if c in df.columns]
    if preview_cols:
        print(f"  {df[preview_cols].head(5).to_string()}")
    
    ans = input(f"\n  确认处理结果? (Y/n): ").strip().lower()
    return ans != "n"


# ══════════════════════════════════════════════════════════════════
# 模块6：导出 (Export)
# ══════════════════════════════════════════════════════════════════

def export_step(df: pd.DataFrame, stats: dict, output_path: str = None):
    """步骤4: 导出结果"""
    print(f"\n{'─'*50}")
    print("  [导出] 步骤4：输出报告")
    print(f"{'─'*50}")
    
    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"access_result_{ts}.xlsx"
    
    chart_path = output_path.replace(".xlsx", ".png")
    
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # Sheet1: 处理结果
        df.to_excel(writer, sheet_name="处理结果", index=False)
        
        # Sheet2: 统计汇总
        summary_rows = []
        summary_rows.append({"指标": "总记录数", "数值": stats["total"]})
        summary_rows.append({"指标": "正常记录", "数值": stats["normal"]})
        summary_rows.append({"指标": "异常记录", "数值": stats["anomaly"]})
        summary_rows.append({"指标": "及时率(%)", "数值": stats["rate"]})
        summary_df = pd.DataFrame(summary_rows)
        summary_df.to_excel(writer, sheet_name="统计汇总", index=False)
        
        # Sheet3: 按站点统计
        if stats.get("site_stats"):
            site_rows = []
            for site, s in stats["site_stats"].items():
                site_rows.append({
                    "站点": site, "总记录": s["total"], "正常": s["normal"],
                    "异常": s["anomaly"], "及时率(%)": s["rate"]
                })
            pd.DataFrame(site_rows).to_excel(writer, sheet_name="站点统计", index=False)
        
        # Sheet4: 异常记录
        anomaly_df = df[df["是否超时"].notna() & (df["是否超时"] != "")]
        if len(anomaly_df) > 0:
            anomaly_df.to_excel(writer, sheet_name="异常记录", index=False)
    
    # 生成图表
    visualize(df, chart_path)
    
    print(f"\n  ✓ 导出成功!")
    print(f"  ├─ Excel: {os.path.abspath(output_path)}")
    if os.path.exists(chart_path):
        print(f"  └─ 图表: {os.path.abspath(chart_path)}")
    
    return output_path


# ══════════════════════════════════════════════════════════════════
# 交互式主循环 (Input → Filter → Process → Check → Export)
# ══════════════════════════════════════════════════════════════════

def interactive_loop():
    """完整交互式闭环"""
    print(f"\n{'█'*60}")
    print(f"█  门禁考勤数据自动化处理 v{VERSION}")
    print(f"█  交互式闭环: 输入→筛选→处理→检查→导出")
    print(f"{'█'*60}")
    
    if not DEP_OK:
        print("\n❌ 需要安装依赖:")
        print("   pip install pandas openpyxl matplotlib")
        return
    
    print("\n可用命令:")
    print("  load <file>   加载数据")
    print("  filter        筛选数据")
    print("  process       执行处理")
    print("  check         检查结果")
    print("  export <path> 导出报告")
    print("  show          预览数据")
    print("  stats         查看统计")
    print("  reset         重置数据")
    print("  help          帮助")
    print("  quit          退出")
    
    raw_data = None      # 原始数据（保留备份）
    data = None          # 当前数据
    col_map = {}
    result = None
    stats = None
    file_loaded = False
    
    while True:
        cmd = input(f"\n{'→' if file_loaded else '○'} ").strip()
        
        if cmd == "quit":
            print("再见!")
            break
        
        elif cmd == "help":
            print("\n┌─ 命令说明 ──────────────────────────────")
            print("│ load <file>   加载Excel/CSV文件")
            print("│ filter        按站点/人员/日期筛选数据")
            print("│ process       执行完整业务处理")
            print("│ check         检查处理结果")
            print("│ export <path> 导出为格式化Excel+图表")
            print("│ show          预览当前数据前10行")
            print("│ stats         显示统计信息")
            print("│ reset         重置到原始加载数据")
            print("│ help          显示本帮助")
            print("│ quit          退出")
            print("└──────────────────────────────────────────")
        
        elif cmd.startswith("load "):
            fp = cmd[5:].strip()
            try:
                raw_data, col_map = load_step(fp)
                data = raw_data.copy()
                file_loaded = True
                
                # 加载后检查
                if col_map["time_col"] is None:
                    print("  ⚠ 未识别到时间列。输入列名手动指定（或留空继续）:")
                    for i, c in enumerate(data.columns, 1):
                        print(f"     {i}. {c}")
                    sel = input("  时间列编号/名称: ").strip()
                    if sel:
                        if sel.isdigit() and 1 <= int(sel) <= len(data.columns):
                            col_map["time_col"] = data.columns[int(sel) - 1]
                        elif sel in data.columns:
                            col_map["time_col"] = sel
                        print(f"  → 时间列 = {col_map['time_col']}")
            except Exception as e:
                print(f"  ❌ 加载失败: {e}")
        
        elif cmd == "filter":
            if not file_loaded:
                print("  ⚠ 请先用 load 加载数据")
                continue
            data = filter_step(data, col_map)
        
        elif cmd == "process":
            if not file_loaded:
                print("  ⚠ 请先用 load 加载数据")
                continue
            data = process_step(data, col_map)
            stats = calc_timeliness(data)
            print(f"\n  及时率: {stats['rate']}% ({stats['normal']}/{stats['total']})")
        
        elif cmd == "check":
            if data is None:
                print("  ⚠ 无数据可检查")
                continue
            check_process(data)
        
        elif cmd.startswith("export "):
            if data is None:
                print("  ⚠ 请先用 process 完成处理")
                continue
            fp = cmd[7:].strip() or None
            if stats is None:
                stats = calc_timeliness(data)
            export_step(data, stats, fp)
            
            # 导出后检查
            if fp and os.path.exists(fp):
                print(f"  ✓ 文件验证: {os.path.getsize(fp)/1024:.1f} KB")
        
        elif cmd == "show":
            if data is None:
                print("  ⚠ 无数据")
                continue
            print(f"\n  前10行 (共{len(data)}行):")
            print(data.head(10).to_string())
        
        elif cmd == "stats":
            if data is None:
                print("  ⚠ 无数据")
                continue
            if stats:
                print(f"\n  及时率: {stats['rate']}%")
                print(f"  总记录: {stats['total']} | 正常: {stats['normal']} | 异常: {stats['anomaly']}")
                if stats.get("site_stats"):
                    print(f"  站点详情:")
                    for site, s in stats["site_stats"].items():
                        print(f"    {site}: {s['rate']}% ({s['normal']}/{s['total']})")
                # 文字总结
                print(f"\n  文字总结:")
                for line in generate_summary(stats):
                    print(f"    {line}")
            else:
                print(data.describe().to_string())
        
        elif cmd == "reset":
            if raw_data is not None:
                data = raw_data.copy()
                stats = None
                print("  ✓ 已重置到原始数据")
        
        elif cmd:
            print(f"  未知命令: {cmd}，输入 help 查看")


# ══════════════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if not DEP_OK:
        print("=" * 60)
        print("  需要安装依赖:")
        print("    pip install pandas openpyxl matplotlib")
        print("=" * 60)
        sys.exit(1)
    
    # 命令行参数模式
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        fp = sys.argv[1]
        if os.path.exists(fp):
            # 全自动模式
            auto_all = "--all" in sys.argv
            
            try:
                df, col_map = load_step(fp)
                if auto_all:
                    df = filter_step(df, col_map)
                df = process_step(df, col_map)
                if check_process(df):
                    stats = calc_timeliness(df)
                    # 生成总结
                    print(f"\n  ┌─ 文字总结:")
                    for line in generate_summary(stats):
                        print(f"  │  {line}")
                    print(f"  └─")
                    out = export_step(df, stats)
                    print(f"\n✅ 处理完成! 输出: {out}")
                else:
                    print("⚠ 用户取消导出")
            except Exception as e:
                print(f"❌ 处理失败: {e}")
        else:
            print(f"❌ 文件不存在: {sys.argv[1]}")
            interactive_loop()
    else:
        interactive_loop()
