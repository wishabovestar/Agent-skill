#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
门禁考勤数据自动化处理系统
============================
交互式Python程序：输入/筛选→检索→功能调用→检查
基于用户真实需求构建（来自微信截图OCR识别分析）

功能模块:
  1. load_data()     - 加载Excel门禁数据
  2. classify_period()- 按时间规则分类工作时段
  3. calc_timespan()  - 计算进出时间跨度
  4. detect_anomaly() - 检测异常记录
  5. filter_data()    - 按条件筛选/排除
  6. calc_rate()      - 统计及时率
  7. visualize()      - 生成可视化图表
  8. export_report()  - 导出格式化报告

使用方法:
  python access_control_automation.py          # 交互模式
  python access_control_automation.py <file>   # 直接处理文件

时间规则:
  - 上午工作时段: 09:00 - 11:50
  - 下午工作时段: 13:30 - 18:20
  - 时间跨度阈值: <15min=过短异常, >240min=超时异常
"""

import sys
import os
import re
from pathlib import Path
from datetime import datetime, time, timedelta
from typing import Optional
import warnings
warnings.filterwarnings("ignore")

try:
    import pandas as pd
    import numpy as np
    PANDAS_OK = True
except ImportError:
    PANDAS_OK = False
    print("⚠ 建议安装pandas: pip install pandas openpyxl")

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    MATPLOTLIB_OK = True
except ImportError:
    MATPLOTLIB_OK = False

# ============================================================
# 配置
# ============================================================

# 工作时段定义
MORNING_START = time(9, 0, 0)
MORNING_END = time(11, 50, 0)
AFTERNOON_START = time(13, 30, 0)
AFTERNOON_END = time(18, 20, 0)

# 异常阈值（分钟）
ANOMALY_MIN = 15      # 低于此值 → 过短异常
ANOMALY_MAX = 240     # 高于此值 → 超时异常

# 输出格式
OUTPUT_FONT = "Microsoft YaHei"  # 微软雅黑
OUTPUT_FONT_SIZE = 9

# 列名映射（根据用户Excel截图）
COLUMN_MAP = {
    "A": "序号",
    "B": "日期",
    "C": "时间",
    "D": "区域",
    "E": "姓名/工号",
    "F": "进出方向",
    "G": "设备编号",
    "H": "站点",
    "I": "实测数量",    # 用户提到的I列
    "J": "预留",
    "K": "工作时段",    # IF(OR(AND(...)))判断
    "L": "标识",        # 填充"2"
    "M": "时间跨度/min", # =IF(F3=F2,(A3-A2)*1440,"")
    "N": "进出详情",    # CHOOSE公式
    "O": "是否超时",    # IF(AND(M2>15,M2<240)...)
    "P": "错误类型",
    "Q": "判断依据1",
    "R": "判断依据2",
    "S": "判断依据3",
}


# ============================================================
# 1. 核心函数模块
# ============================================================

def load_data(filepath: str) -> pd.DataFrame:
    """加载门禁数据（支持.xlsx/.xls/.csv）"""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")
    
    ext = path.suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(filepath, encoding="utf-8-sig")
    elif ext in (".xlsx", ".xls"):
        df = pd.read_excel(filepath, engine="openpyxl" if ext == ".xlsx" else "xlrd")
    else:
        raise ValueError(f"不支持的文件格式: {ext}，请使用.xlsx/.xls/.csv")
    
    print(f"✓ 已加载数据: {len(df)} 行, {len(df.columns)} 列")
    print(f"  列名: {list(df.columns)}")
    return df


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """标准化列名（自动匹配用户Excel截图中的列）"""
    df = df.copy()
    # 尝试识别时间列
    time_col = None
    date_col = None
    name_col = None
    direction_col = None
    device_col = None
    site_col = None
    
    for col in df.columns:
        col_lower = str(col).lower()
        if any(k in col_lower for k in ["时间", "time", "时刻"]):
            time_col = col
        elif any(k in col_lower for k in ["日期", "date", "日"]):
            date_col = col
        elif any(k in col_lower for k in ["姓名", "工号", "name", "人员", "员工"]):
            name_col = col
        elif any(k in col_lower for k in ["进出", "方向", "进/出", "方向"]):
            direction_col = col
        elif any(k in col_lower for k in ["设备", "device", "编号"]):
            device_col = col
        elif any(k in col_lower for k in ["站点", "site", "地点", "区域"]):
            site_col = col
    
    return df, {
        "time_col": time_col,
        "date_col": date_col,
        "name_col": name_col,
        "direction_col": direction_col,
        "device_col": device_col,
        "site_col": site_col,
    }


def classify_work_period(dt: datetime) -> str:
    """按时间规则分类工作时段"""
    t = dt.time()
    if MORNING_START <= t <= MORNING_END:
        return "上午工作时段"
    elif AFTERNOON_START <= t <= AFTERNOON_END:
        return "下午工作时段"
    else:
        return "非工作时段"


def calc_timespan(df: pd.DataFrame, time_col: str, group_col: str = None) -> pd.Series:
    """计算连续记录间的时间跨度（分钟）"""
    if group_col:
        # 按人/设备分组计算
        result = df.groupby(group_col)[time_col].diff().dt.total_seconds() / 60
    else:
        # 全局顺序计算
        result = df[time_col].diff().dt.total_seconds() / 60
    return result.fillna(0).round(1)


def detect_anomaly(timespan_min: float) -> str:
    """检测时间跨度异常"""
    if timespan_min == 0:
        return ""  # 首条记录
    elif timespan_min < ANOMALY_MIN:
        return "过短异常"
    elif timespan_min > ANOMALY_MAX:
        return "超时异常"
    else:
        return "正常"


def classify_entry_detail(period: str, timespan: float, anomaly: str) -> str:
    """分类进出详情（对应N列CHOOSE逻辑）"""
    if pd.isna(timespan) or timespan == 0:
        return "首次记录"
    if anomaly == "过短异常":
        return f"快速往返({timespan:.0f}min)"
    elif anomaly == "超时异常":
        return f"长时间停留({timespan:.0f}min)"
    else:
        if period == "上午工作时段":
            return "上午正常进出"
        elif period == "下午工作时段":
            return "下午正常进出"
        else:
            return f"非工作时段进出({timespan:.0f}min)"


# ============================================================
# 2. 交互式数据筛选
# ============================================================

def interactive_filter(df: pd.DataFrame) -> pd.DataFrame:
    """交互式筛选数据（用户输入条件）"""
    print("\n" + "=" * 60)
    print("  数据筛选 - 请输入筛选条件（留空=跳过）")
    print("=" * 60)
    
    result = df.copy()
    cols = list(result.columns)
    
    print(f"\n可用列: {', '.join(cols[:10])}")
    if len(cols) > 10:
        print(f"        ... 还有{len(cols)-10}列")
    
    # 按站点筛选
    site_cols = [c for c in cols if any(k in str(c).lower() for k in ["站点", "地点", "site", "区域"])]
    if site_cols:
        sc = site_cols[0]
        sites = result[sc].dropna().unique()
        print(f"\n站点列表 ({sc}):")
        for i, s in enumerate(sites[:10], 1):
            print(f"  {i}. {s}")
        if len(sites) > 10:
            print(f"  ... 还有{len(sites)-10}个站点")
        site_input = input("\n要筛选的站点（输入编号/名称，留空=全部）: ").strip()
        if site_input:
            if site_input.isdigit():
                idx = int(site_input) - 1
                if 0 <= idx < len(sites):
                    result = result[result[sc] == sites[idx]]
            else:
                result = result[result[sc].astype(str).str.contains(site_input, na=False)]
            print(f"  → 筛选后: {len(result)} 行")
    
    # 按人员筛选
    name_cols = [c for c in cols if any(k in str(c).lower() for k in ["姓名", "工号", "name", "人员"])]
    if name_cols:
        nc = name_cols[0]
        print(f"\n人员列: {nc}")
        name_input = input("要筛选的人员关键词（留空=全部）: ").strip()
        if name_input:
            result = result[result[nc].astype(str).str.contains(name_input, na=False)]
            print(f"  → 筛选后: {len(result)} 行")
    
    # 按日期范围筛选
    date_cols = [c for c in cols if any(k in str(c).lower() for k in ["日期", "date"])]
    if date_cols:
        dc = date_cols[0]
        date_range = input("\n日期范围（格式: 2026-01-01~2026-01-31，留空=全部）: ").strip()
        if date_range and "~" in date_range:
            try:
                start, end = date_range.split("~")
                result[dc] = pd.to_datetime(result[dc])
                mask = (result[dc] >= pd.to_datetime(start.strip())) & \
                       (result[dc] <= pd.to_datetime(end.strip()))
                result = result[mask]
                print(f"  → 筛选后: {len(result)} 行")
            except:
                print("  ⚠ 日期格式错误，跳过")
    
    return result


def select_sites() -> list:
    """选择要处理的站点"""
    print("\n可处理站点: 1)珠海  2)重庆  3)马来西亚  4)全部")
    choice = input("选择（输入编号，多选用逗号分隔）: ").strip()
    site_map = {"1": "珠海", "2": "重庆", "3": "马来西亚", "4": "全部"}
    if choice == "4" or not choice:
        return ["珠海", "重庆", "马来西亚"]
    sites = []
    for c in choice.split(","):
        c = c.strip()
        if c in site_map:
            sites.append(site_map[c])
    return sites if sites else ["珠海", "重庆", "马来西亚"]


# ============================================================
# 3. 统计分析
# ============================================================

def calc_timeliness_rate(df: pd.DataFrame) -> dict:
    """统计及时率"""
    total = len(df)
    if total == 0:
        return {"total": 0, "normal": 0, "anomaly": 0, "rate": 0}
    
    anomaly_count = len(df[df["是否超时"].notna() & (df["是否超时"] != "")])
    normal_count = total - anomaly_count
    rate = round(normal_count / total * 100, 2) if total > 0 else 0
    
    return {
        "total": total,
        "normal": normal_count,
        "anomaly": anomaly_count,
        "rate": rate,
    }


def generate_summary(stats: dict, site: str = "") -> str:
    """生成文字总结（1~3行）"""
    lines = []
    prefix = f"[{site}] " if site else ""
    
    lines.append(f"{prefix}数据统计: 共{stats['total']}条记录, "
                  f"正常{stats['normal']}条, 异常{stats['anomaly']}条, "
                  f"及时率{stats['rate']}%")
    
    if stats['anomaly'] > 0:
        ratio = stats['anomaly'] / stats['total'] * 100
        lines.append(f"{prefix}需关注: 异常占比{ratio:.1f}%, "
                      f"建议核查{'/'.join(stats.get('top_anomalies', []))}")
    
    if stats['rate'] >= 95:
        lines.append(f"{prefix}整体运行良好，及时率达标")
    elif stats['rate'] >= 80:
        lines.append(f"{prefix}及时率尚可，仍有优化空间")
    else:
        lines.append(f"{prefix}及时率偏低，建议排查流程问题")
    
    return "\n".join(lines)


# ============================================================
# 4. 可视化
# ============================================================

def visualize_results(df: pd.DataFrame, output_path: str = "access_analysis.png"):
    """生成可视化图表"""
    if not MATPLOTLIB_OK:
        print("⚠ matplotlib不可用，跳过可视化")
        return
    
    # 尝试设置中文字体
    try:
        plt.rcParams['font.sans-serif'] = [OUTPUT_FONT, 'SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
    except:
        pass
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("门禁考勤数据分析报告", fontsize=14, fontweight='bold')
    
    # 1. 各站点记录数
    if "区域" in df.columns:
        site_counts = df["区域"].value_counts()
        axes[0, 0].bar(site_counts.index, site_counts.values, color='steelblue')
        axes[0, 0].set_title("各站点记录数")
        axes[0, 0].tick_params(axis='x', rotation=45)
    
    # 2. 时间跨度分布
    if "时间跨度/min" in df.columns:
        spans = df["时间跨度/min"].dropna()
        spans = spans[spans < 500]  # 排除极端值
        axes[0, 1].hist(spans, bins=30, color='coral', alpha=0.7, edgecolor='white')
        axes[0, 1].axvline(x=15, color='red', linestyle='--', alpha=0.5, label='阈值15min')
        axes[0, 1].axvline(x=240, color='red', linestyle='--', alpha=0.5, label='阈值240min')
        axes[0, 1].set_title("时间跨度分布")
        axes[0, 1].set_xlabel("时间跨度/min")
        axes[0, 1].legend()
    
    # 3. 工作时段分布
    if "工作时段" in df.columns:
        period_counts = df["工作时段"].value_counts()
        axes[1, 0].pie(period_counts.values, labels=period_counts.index, 
                       autopct='%1.1f%%', colors=['#66b3ff', '#ff9999', '#99ff99'])
        axes[1, 0].set_title("工作时段分布")
    
    # 4. 异常类型分布
    if "是否超时" in df.columns:
        anomaly_counts = df["是否超时"].value_counts()
        axes[1, 1].bar(anomaly_counts.index, anomaly_counts.values, color=['#2ecc71', '#e74c3c', '#f39c12'])
        axes[1, 1].set_title("异常类型分布")
        axes[1, 1].tick_params(axis='x', rotation=45)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"✓ 图表已保存: {output_path}")
    plt.close()


# ============================================================
# 5. 主处理流程
# ============================================================

def process_data(filepath: str, output_dir: str = ".") -> dict:
    """完整数据处理流程"""
    print("\n" + "█" * 60)
    print("█  门禁考勤数据自动化处理")
    print("█" * 60)
    
    # 1. 加载数据
    print("\n[步骤1/7] 加载数据...")
    df = load_data(filepath)
    
    # 2. 标准化列名
    print("\n[步骤2/7] 识别列结构...")
    df, col_map = normalize_columns(df)
    if col_map["time_col"]:
        print(f"  → 时间列: {col_map['time_col']}")
    if col_map["date_col"]:
        print(f"  → 日期列: {col_map['date_col']}")
        df[col_map["date_col"]] = pd.to_datetime(df[col_map["date_col"]])
    
    # 3. 交互/自动筛选
    print("\n[步骤3/7] 数据筛选...")
    interactive = input("\n是否进入交互筛选模式? (y/N): ").strip().lower() == 'y'
    if interactive:
        df = interactive_filter(df)
    else:
        print("  → 使用全部数据")
    
    # 4. 时间跨度计算
    print("\n[步骤4/7] 计算时间跨度...")
    time_col = col_map.get("time_col")
    if time_col:
        df[time_col] = pd.to_datetime(df[time_col])
        
        # 计算工作时段
        df["工作时段"] = df[time_col].apply(classify_work_period)
        
        # 计算时间跨度
        df["时间跨度/min"] = calc_timespan(df, time_col, col_map.get("name_col"))
        
        # 检测异常
        df["是否超时"] = df["时间跨度/min"].apply(detect_anomaly)
        
        # 进出详情
        df["进出详情"] = df.apply(
            lambda r: classify_entry_detail(r["工作时段"], r["时间跨度/min"], r["是否超时"]),
            axis=1
        )
        print(f"  → 时间跨度计算完成，异常记录: {(df['是否超时']!='').sum()}")
    
    # 5. 统计
    print("\n[步骤5/7] 统计及时率...")
    stats = calc_timeliness_rate(df)
    print(f"  → 总记录: {stats['total']}")
    print(f"  → 正常: {stats['normal']}  |  异常: {stats['anomaly']}")
    print(f"  → 及时率: {stats['rate']}%")
    
    summary = generate_summary(stats)
    print(f"\n  文字总结:\n{summary}")
    
    # 6. 可视化
    print("\n[步骤6/7] 生成图表...")
    chart_path = os.path.join(output_dir, "access_analysis.png")
    visualize_results(df, chart_path)
    
    # 7. 导出结果
    print("\n[步骤7/7] 导出报告...")
    output_file = os.path.join(output_dir, "access_processed_result.xlsx")
    
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # 主数据表
        df.to_excel(writer, sheet_name="处理结果", index=False)
        
        # 统计汇总表
        summary_df = pd.DataFrame([stats])
        summary_df.to_excel(writer, sheet_name="统计汇总", index=False)
        
        # 异常记录表
        anomaly_df = df[df["是否超时"].notna() & (df["是否超时"] != "")]
        if len(anomaly_df) > 0:
            anomaly_df.to_excel(writer, sheet_name="异常记录", index=False)
    
    print(f"  → 报告已保存: {output_file}")
    print(f"\n{'='*60}")
    print(f"  处理完成！输出文件:")
    print(f"    - 数据结果: {output_file}")
    print(f"    - 图表:     {chart_path}")
    print(f"{'='*60}")
    
    return {
        "data": df,
        "stats": stats,
        "summary": summary,
        "outputs": [output_file, chart_path],
    }


# ============================================================
# 6. 入口
# ============================================================

def interactive_shell():
    """交互式命令行模式"""
    print("\n" + "█" * 60)
    print("█  门禁考勤数据自动化处理系统 (交互模式)")
    print("█" * 60)
    print("\n可用命令:")
    print("  load <file>     - 加载Excel/CSV数据")
    print("  filter          - 交互筛选数据")
    print("  process         - 执行完整处理流程")
    print("  stats           - 查看统计信息")
    print("  chart           - 生成图表")
    print("  export <path>   - 导出结果")
    print("  help            - 帮助")
    print("  quit            - 退出")
    print("-" * 40)
    
    data = None
    result = None
    
    while True:
        cmd = input("\n> ").strip().lower()
        
        if cmd == "quit":
            break
        elif cmd.startswith("load "):
            filepath = cmd[5:].strip()
            if os.path.exists(filepath):
                data = load_data(filepath)
                data, col_map = normalize_columns(data)
            else:
                print(f"⚠ 文件不存在: {filepath}")
        elif cmd == "filter":
            if data is not None:
                data = interactive_filter(data)
            else:
                print("⚠ 请先 load 数据")
        elif cmd == "process":
            if data is not None:
                result = process_data(data)
            else:
                print("⚠ 请先 load 数据")
        elif cmd == "stats":
            if data is not None:
                print(data.describe())
            else:
                print("⚠ 请先 load 数据")
        elif cmd == "chart":
            if data is not None:
                visualize_results(data)
            else:
                print("⚠ 请先 load 数据")
        elif cmd.startswith("export "):
            path = cmd[7:].strip()
            if data is not None:
                data.to_excel(path, index=False)
                print(f"✓ 已导出: {path}")
            else:
                print("⚠ 请先 load 数据")
        elif cmd == "help":
            print("\n命令说明:")
            print("  load <file.xlsx>  - 加载Excel文件")
            print("  filter            - 按站点/人员/日期范围筛选")
            print("  process           - 执行完整流程（时段分类+跨度计算+异常检测+统计）")
            print("  stats             - 显示数据摘要")
            print("  chart             - 生成可视化图表")
            print("  export <path>     - 导出DataFrame到Excel")
            print("  quit              - 退出\n")
        elif cmd:
            print(f"未知命令: {cmd}，输入 help 查看帮助")


if __name__ == "__main__":
    # 检查依赖
    if not PANDAS_OK:
        print("=" * 60)
        print("  需要安装依赖:")
        print("    pip install pandas openpyxl matplotlib")
        print("=" * 60)
        sys.exit(1)
    
    # 命令行参数模式
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        process_data(sys.argv[1])
    else:
        # 交互模式
        if len(sys.argv) > 1:
            print(f"⚠ 文件不存在: {sys.argv[1]}")
        interactive_shell()
