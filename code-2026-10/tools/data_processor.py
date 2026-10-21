#!/usr/bin/env python3
"""
数据处理 Agent 流水线 v1.0
=======================================
配合 data_encoder.py 使用，实现：
1. OCR 识别编码图片 → 还原数据
2. 数据清洗/整理/排列
3. 特征识别与筛选
4. 数据可视化
5. 生成可复用的数据处理 Python 代码

用法:
  python data_processor.py output/ --ocr
  python data_processor.py output/ --clean
  python data_processor.py output/ --stats
  python data_processor.py output/ --plot
  python data_processor.py output/ --codegen
"""

import argparse
import csv
import json
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import Counter, defaultdict


# ── OCR 引擎 ──────────────────────────────────────
try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pandas as pd
    import numpy as np
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

# ── 可视化 ────────────────────────────────────────
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


# ── 数据容器 ──────────────────────────────────────

@dataclass
class DataTable:
    """统一数据表容器"""
    headers: List[str]
    rows: List[List[str]]
    name: str = "data"
    source_images: List[str] = field(default_factory=list)
    
    def to_dataframe(self) -> "pd.DataFrame":
        """转为 pandas DataFrame"""
        if not HAS_PANDAS:
            raise ImportError("需要 pandas")
        return pd.DataFrame(self.rows, columns=self.headers)
    
    @property
    def shape(self) -> Tuple[int, int]:
        return (len(self.headers), len(self.rows))
    
    def summary(self) -> str:
        lines = [f"📊 {self.name}: {self.shape[0]}列 × {self.shape[1]}行"]
        if self.source_images:
            lines.append(f"   来源图片: {len(self.source_images)}张")
        lines.append(f"   列名: {', '.join(self.headers[:8])}{'...' if len(self.headers)>8 else ''}")
        return "\n".join(lines)


# ── OCR 识别 ──────────────────────────────────────

def ocr_image(image_path: str) -> str:
    """OCR识别单张图片，返回结构化文本"""
    if not HAS_TESSERACT or not HAS_PIL:
        return f"[OCR不可用: 需安装 pytesseract + tesseract-ocr]"
    
    img = Image.open(image_path)
    # 提高OCR精度：放大+二值化
    w, h = img.size
    if w < 1000 or h < 1000:
        img = img.resize((w * 2, h * 2), Image.LANCZOS)
    
    # 配置：PSM 6=统一文本块，oem 3=默认引擎
    custom_config = r"--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.,-+/%%()[]{}@#_=:;!?%% "
    try:
        text = pytesseract.image_to_string(img, lang="eng+chi_sim", config=custom_config)
        return text.strip()
    except Exception as e:
        return f"[OCR错误: {e}]"


def batch_ocr(image_dir: str) -> Dict[str, str]:
    """批量OCR目录下所有编码图片"""
    results = {}
    img_dir = Path(image_dir)
    patterns = ["*.png", "*.jpg", "*.jpeg"]
    for pattern in patterns:
        for img_path in sorted(img_dir.glob(pattern)):
            text = ocr_image(str(img_path))
            results[img_path.name] = text
            print(f"  🔍 {img_path.name}: {len(text)}字符已识别")
    return results


def parse_ocr_text(text: str) -> Tuple[List[str], List[List[str]]]:
    """将OCR文本解析为结构化表格"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return [], []
    
    # 跳过标题行（含"部分"、"列"等标记）
    data_lines = []
    for line in lines:
        if any(kw in line for kw in ["部分", "列", "行"]):
            if "|" not in line and "\t" not in line:
                continue
        data_lines.append(line)
    
    if not data_lines:
        return [], []
    
    # 尝试多种分隔符
    separators = ["|", "\t", ","]
    best_sep = None
    best_count = 0
    for sep in separators:
        counts = [line.count(sep) for line in data_lines[:5]]
        if counts and sum(counts) > best_count:
            best_count = sum(counts)
            best_sep = sep
    
    if not best_sep or best_count == 0:
        # 空格分隔（固定宽度）
        return parse_fixed_width(data_lines)
    
    parsed = []
    for line in data_lines:
        cells = [c.strip() for c in line.split(best_sep)]
        parsed.append(cells)
    
    if not parsed:
        return [], []
    
    # 第一行作为表头
    headers = parsed[0]
    rows = parsed[1:] if len(parsed) > 1 else []
    
    # 补齐行
    max_cols = len(headers)
    rows = [row + [""] * (max_cols - len(row)) for row in rows]
    rows = [row[:max_cols] for row in rows]
    
    return headers, rows


def parse_fixed_width(lines: List[str]) -> Tuple[List[str], List[List[str]]]:
    """解析固定宽度文本（空格对齐）"""
    if not lines:
        return [], []
    
    # 检测列边界
    # 简单方案：按连续空格分割
    parsed = []
    for line in lines:
        cells = re.split(r"\s{2,}", line)
        parsed.append([c.strip() for c in cells if c.strip()])
    
    if not parsed:
        return [], []
    
    headers = parsed[0] if parsed else []
    rows = parsed[1:] if len(parsed) > 1 else []
    
    max_cols = len(headers)
    rows = [row + [""] * (max_cols - len(row)) for row in rows]
    rows = [row[:max_cols] for row in rows]
    
    return headers, rows


# ── 数据清洗 ──────────────────────────────────────

def auto_detect_types(rows: List[List[str]]) -> List[str]:
    """自动推断每列数据类型"""
    if not rows:
        return []
    types = []
    for ci in range(len(rows[0])):
        col_vals = [row[ci] for row in rows if row[ci].strip()]
        if not col_vals:
            types.append("str")
            continue
        # 检查是否为数值
        numeric = 0
        for v in col_vals:
            v_clean = v.replace(",", "").replace("%", "").replace("$", "")
            try:
                float(v_clean)
                numeric += 1
            except ValueError:
                pass
        if numeric > len(col_vals) * 0.7:
            types.append("numeric")
        else:
            types.append("str")
    return types


def clean_data(headers: List[str], rows: List[List[str]], 
               strip: bool = True, drop_empty_rows: bool = True,
               fill_na: str = "") -> Tuple[List[str], List[List[str]]]:
    """数据清洗"""
    cleaned_rows = []
    for row in rows:
        if strip:
            row = [c.strip() if c else "" for c in row]
        if drop_empty_rows and all(not c for c in row):
            continue
        if fill_na is not None:
            row = [c if c else fill_na for c in row]
        cleaned_rows.append(row)
    
    return headers, cleaned_rows


def get_statistics(headers: List[str], rows: List[List[str]]) -> Dict:
    """生成基本统计信息"""
    if not rows:
        return {"error": "无数据"}
    
    types = auto_detect_types(rows)
    stats = {
        "shape": [len(headers), len(rows)],
        "columns": {},
    }
    
    for ci, h in enumerate(headers):
        col_vals = [row[ci] for row in rows if row[ci].strip()]
        col_info = {
            "type": types[ci] if ci < len(types) else "str",
            "non_null": len(col_vals),
            "null_count": len(rows) - len(col_vals),
        }
        
        if types[ci] == "numeric":
            nums = []
            for v in col_vals:
                try:
                    nums.append(float(v.replace(",", "").replace("%", "").replace("$", "")))
                except ValueError:
                    pass
            if nums:
                col_info.update({
                    "min": round(min(nums), 4),
                    "max": round(max(nums), 4),
                    "mean": round(np.mean(nums), 4) if HAS_PANDAS else round(sum(nums)/len(nums), 4),
                    "median": round(sorted(nums)[len(nums)//2], 4),
                    "std": round(np.std(nums), 4) if HAS_PANDAS else 0,
                })
        else:
            # 字符串列：频率统计
            freq = Counter(col_vals)
            col_info["unique"] = len(freq)
            col_info["top5"] = freq.most_common(5)
        
        stats["columns"][h] = col_info
    
    return stats


# ── 可视化 ────────────────────────────────────────

def plot_data(headers: List[str], rows: List[List[str]], 
              output_dir: str = "plots", prefix: str = "plot") -> List[str]:
    """自动生成数据可视化图表"""
    if not HAS_MPL or not HAS_PANDAS:
        return ["[可视化不可用: 需安装 matplotlib + pandas]"]
    
    df = pd.DataFrame(rows, columns=headers)
    types = auto_detect_types(rows)
    
    # 自动转换数值列
    for ci, t in enumerate(types):
        if t == "numeric":
            df[headers[ci]] = pd.to_numeric(
                df[headers[ci]].str.replace(",", "").str.replace("%", "").str.replace("$", ""),
                errors="coerce"
            )
    
    os.makedirs(output_dir, exist_ok=True)
    saved = []
    
    numeric_cols = [h for ci, h in enumerate(headers) if ci < len(types) and types[ci] == "numeric"]
    str_cols = [h for ci, h in enumerate(headers) if ci >= len(types) or types[ci] != "numeric"]
    
    # 图1: 数值列分布（直方图）
    if numeric_cols:
        fig, axes = plt.subplots(min(3, len(numeric_cols)), 1, figsize=(12, 4*min(3, len(numeric_cols))))
        if len(numeric_cols) == 1:
            axes = [axes]
        for ax, col in zip(axes, numeric_cols[:3]):
            df[col].hist(bins=20, ax=ax, color="steelblue", edgecolor="black")
            ax.set_title(f"{col} 分布", fontsize=12, fontweight="bold")
            ax.set_xlabel(col)
            ax.set_ylabel("频数")
        path = os.path.join(output_dir, f"{prefix}_distribution.png")
        plt.tight_layout()
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        saved.append(path)
        print(f"  ✅ {path}")
    
    # 图2: 数值列对比（散点矩阵）
    if len(numeric_cols) >= 2:
        fig, ax = plt.subplots(figsize=(10, 8))
        pd.plotting.scatter_matrix(df[numeric_cols[:4]], figsize=(10, 10), ax=ax)
        path = os.path.join(output_dir, f"{prefix}_scatter.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        saved.append(path)
        print(f"  ✅ {path}")
    
    # 图3: 类别统计（柱状图）
    if str_cols:
        n_plots = min(2, len(str_cols))
        fig, axes = plt.subplots(1, n_plots, figsize=(8*n_plots, 5))
        if n_plots == 1:
            axes = [axes]
        for ax, col in zip(axes, str_cols[:2]):
            top10 = df[col].value_counts().head(10)
            top10.plot(kind="barh", ax=ax, color="coral", edgecolor="black")
            ax.set_title(f"{col} Top10", fontsize=12, fontweight="bold")
            ax.set_xlabel("计数")
        path = os.path.join(output_dir, f"{prefix}_categories.png")
        plt.tight_layout()
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        saved.append(path)
        print(f"  ✅ {path}")
    
    # 图4: 趋势图（如果有一列可作X轴）
    if numeric_cols:
        fig, ax = plt.subplots(figsize=(12, 5))
        for col in numeric_cols[:3]:
            df[col].plot(ax=ax, label=col, linewidth=2, marker="o", markersize=3)
        ax.set_title("数值趋势", fontsize=12, fontweight="bold")
        ax.set_xlabel("行索引")
        ax.legend()
        ax.grid(True, alpha=0.3)
        path = os.path.join(output_dir, f"{prefix}_trend.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        saved.append(path)
        print(f"  ✅ {path}")
    
    return saved


# ── 代码生成 ──────────────────────────────────────

def generate_code(headers: List[str], rows: List[List[str]], 
                  types: List[str], name: str = "data") -> str:
    """生成可复用的数据处理Python代码"""
    # 先计算所有模板变量
    import datetime
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # 类型转换
    conversions = []
    for ci, h in enumerate(headers):
        if ci < len(types) and types[ci] == "numeric":
            conversions.append(f'    df["{h}"] = pd.to_numeric(df["{h}"].str.replace(",", "").str.replace("%", "").str.replace("$", ""), errors="coerce")')
    type_conversions = "\n".join(conversions[:5]) if conversions else "    # 无数值列需要转换"
    
    # 可视化
    numeric_h = [h for ci, h in enumerate(headers) if ci < len(types) and types[ci] == "numeric"]
    if numeric_h:
        plot_lines = ['    fig, ax = plt.subplots(figsize=(10, 5))']
        for col in numeric_h[:3]:
            plot_lines.append(f'    df["{col}"].plot(ax=ax, label="{col}", marker="o", linewidth=2)')
        plot_lines.append('    ax.set_title("数据趋势")\n    ax.legend()\n    ax.grid(True, alpha=0.3)\n    plt.tight_layout()\n    plt.savefig("output_plot.png", dpi=150)\n    plt.show()')
        numeric_plots = "\n".join(plot_lines)
    else:
        numeric_plots = '    print("无数值列可绘图")'
    
    # 数据样例JSON
    sample = {h: [rows[r][ci] if ci < len(rows[r]) else "" for r in range(min(5, len(rows)))] for ci, h in enumerate(headers)}
    headers_json = json.dumps(sample, ensure_ascii=False)[:400]
    
    code = f'''#!/usr/bin/env python3
"""
数据处理代码 — 自动生成
数据: {name}
维度: {len(headers)}列 × {len(rows)}行
生成时间: {now_str}
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ── 1. 数据加载 ──────────────────────────────────
def load_data():
    """加载数据"""
    data = {headers_json}
    df = pd.DataFrame(data)
    
    # 类型转换
{type_conversions}
    return df

df = load_data()
print(f"数据形状: {{df.shape}}")
print(f"\\n列名: {{list(df.columns)}}")
print(f"\\n前5行:\\n{{df.head()}}")

# ── 2. 数据清洗 ──────────────────────────────────
def clean_data(df):
    df_clean = df.copy()
    df_clean = df_clean.dropna(how="all")
    return df_clean

df = clean_data(df)

# ── 3. 基本统计 ──────────────────────────────────
print(f"\\n=== 基本统计 ===\\n{{df.describe()}}")
missing = df.isnull().sum()
print(f"\\n缺失值:\\n{{missing[missing > 0]}}")

# ── 4. 特征筛选（示例） ──────────────────────────
# filtered = df[df["column_name"] > threshold]

# ── 5. 可视化 ────────────────────────────────────
def plot_data(df):
    """数据可视化"""
{numeric_plots}

plot_data(df)
print("\\n✅ 数据处理完成")
'''
    return code


# ── 主流水线 ──────────────────────────────────────

def run_pipeline(image_dir: str, output_dir: str = "output"):
    """完整数据处理流水线"""
    print("=" * 60)
    print("🔧 数据处理流水线 v1.0")
    print("=" * 60)
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Step 1: OCR
    print("\n[1/5] 🔍 OCR识别图片...")
    ocr_results = batch_ocr(image_dir)
    if not ocr_results:
        print("  ❌ 未找到编码图片")
        return
    
    # Step 2: 解析表格
    print("\n[2/5] 📋 解析表格...")
    all_headers = []
    all_rows = []
    for fname, text in ocr_results.items():
        headers, rows = parse_ocr_text(text)
        if headers:
            all_headers = headers
            all_rows.extend(rows)
            print(f"  ✅ {fname}: {len(headers)}列 × {len(rows)}行")
    
    if not all_headers:
        print("  ❌ 未能解析出有效表格")
        return
    
    table = DataTable(headers=all_headers, rows=all_rows, 
                      name="ocr_data", source_images=list(ocr_results.keys()))
    print(f"\n{table.summary()}")
    
    # Step 3: 数据清洗
    print("\n[3/5] 🧹 数据清洗...")
    clean_h, clean_r = clean_data(table.headers, table.rows)
    types = auto_detect_types(clean_r)
    print(f"  清洗后: {len(clean_h)}列 × {len(clean_r)}行")
    
    # 保存清洗后的CSV
    csv_path = os.path.join(output_dir, "cleaned_data.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(clean_h)
        writer.writerows(clean_r)
    print(f"  ✅ 已保存: {csv_path}")
    
    # Step 4: 统计分析
    print("\n[4/5] 📊 统计分析...")
    stats = get_statistics(clean_h, clean_r)
    if "error" not in stats:
        print(f"  数据维度: {stats['shape'][0]}列 × {stats['shape'][1]}行")
        for col_name, col_info in stats["columns"].items():
            if col_info["type"] == "numeric":
                print(f"  📈 {col_name}: 均值={col_info.get('mean','')} "
                      f"范围=[{col_info.get('min','')}, {col_info.get('max','')}]")
            else:
                print(f"  📝 {col_name}: {col_info.get('unique',0)}个唯一值")
    
    # 保存统计
    stats_path = os.path.join(output_dir, "statistics.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2, default=str)
    print(f"  ✅ 已保存: {stats_path}")
    
    # Step 5: 可视化
    print("\n[5/5] 📈 生成可视化...")
    plot_paths = plot_data(clean_h, clean_r, output_dir)
    
    # Step 6: 代码生成
    print("\n💻 生成数据处理代码...")
    code = generate_code(clean_h, clean_r, types)
    code_path = os.path.join(output_dir, "data_processing.py")
    with open(code_path, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"  ✅ 已保存: {code_path}")
    
    print("\n" + "=" * 60)
    print(f"✅ 流水线完成！所有产出在 {output_dir}/")
    print("=" * 60)
    
    return table


def main():
    parser = argparse.ArgumentParser(
        description="数据处理Agent流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input_dir", help="编码图片目录 (data_encoder.py输出)")
    parser.add_argument("-o", "--output", default="output", help="输出目录")
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.input_dir):
        print(f"❌ 目录不存在: {args.input_dir}")
        return 1
    
    run_pipeline(args.input_dir, args.output)
    return 0


if __name__ == "__main__":
    main()
