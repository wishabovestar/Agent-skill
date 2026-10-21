#!/usr/bin/env python3
"""
数据紧凑化预处理器 v1.0
=================================
在编码为图片前，对数据进行数学层面的冗余消除。
参考: LZ77/字典压缩/差值编码的压缩原理，
但输出为 OCR 可读的纯文本格式。

用法:
  python data_compactor.py data.csv -o compact.txt
  python data_compactor.py data.xlsx --sheet Sheet1 | python data_encoder.py -o output/
"""

import argparse
import csv
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ── 列类型推断 ──────────────────────────────────

class ColumnType:
    """列类型标签"""
    INT = "int"
    FLOAT = "float"
    CATEGORY = "cat"      # 低基数分类 → 字典编码
    TEXT = "text"         # 高基数文本
    DATE = "date"         # 日期
    ID = "id"             # 序列ID → 差值/跳略
    BOOL = "bool"         # 布尔 → 0/1
    CONST = "const"       # 常数列 → 仅存值*1


def infer_column_types(headers: List[str], rows: List[List[str]]) -> List[Tuple[str, str, dict]]:
    """
    推断每列类型，返回 [(col_name, type_tag, metadata)]。
    metadata 包含该列的压缩辅助信息。
    """
    n_cols = len(headers)
    col_info = []
    
    for ci in range(n_cols):
        name = headers[ci]
        vals = [row[ci].strip() for row in rows if row[ci].strip()]
        if not vals:
            col_info.append((name, ColumnType.CONST, {"value": "", "count": 0}))
            continue
        
        unique_vals = set(vals)
        n_unique = len(unique_vals)
        total = len(vals)
        
        # 1. 常数列
        if n_unique == 1:
            col_info.append((name, ColumnType.CONST, {"value": list(unique_vals)[0], "count": total}))
            continue
        
        # 2. 布尔/二值
        if n_unique <= 2 and all(v.lower() in ("0","1","true","false","yes","no","y","n","是","否","×","✓","✅","❌") for v in vals):
            mapping = {v: "0" for v in unique_vals}
            keys = list(unique_vals)
            mapping[keys[0]] = "0"
            mapping[keys[1]] = "1" if len(keys) > 1 else "0"
            col_info.append((name, ColumnType.BOOL, {"mapping": mapping, "key0": keys[0], "key1": keys[1] if len(keys)>1 else ""}))
            continue
        
        # 3. 整数数列
        int_count = sum(1 for v in vals if _is_int(v))
        if int_count > total * 0.85:
            nums = [int(v) for v in vals if _is_int(v)]
            is_sequential = _check_sequential(nums)
            if is_sequential:
                col_info.append((name, ColumnType.ID, {
                    "start": nums[0], "step": is_sequential,
                    "count": len(nums), "format": "delta"
                }))
            else:
                min_v, max_v = min(nums), max(nums)
                col_info.append((name, ColumnType.INT, {
                    "min": min_v, "max": max_v, "range": max_v - min_v,
                    "unique": n_unique
                }))
            continue
        
        # 4. 浮点数列
        float_count = sum(1 for v in vals if _is_float(v))
        if float_count > total * 0.85:
            nums = [float(v) for v in vals if _is_float(v)]
            min_v, max_v = min(nums), max(nums)
            # 计算最优小数位数
            decimals = _optimal_decimals(nums)
            col_info.append((name, ColumnType.FLOAT, {
                "min": min_v, "max": max_v, "decimals": decimals,
                "unique": n_unique
            }))
            continue
        
        # 5. 分类列（低基数 → 字典编码）
        if n_unique <= 20:  # 基数≤20的列做字典编码
            # 构建频率排序的映射
            freq = Counter(vals)
            sorted_vals = [v for v, _ in freq.most_common()]
            code_map = {v: chr(65+i) if i < 26 else f"_{i-26}" for i, v in enumerate(sorted_vals)}
            col_info.append((name, ColumnType.CATEGORY, {
                "n_unique": n_unique,
                "map": code_map,
                "reverse_map": {c: v for v, c in code_map.items()},
            }))
            continue
        
        # 6. 默认：文本
        col_info.append((name, ColumnType.TEXT, {
            "max_len": max(len(v) for v in vals),
            "unique": n_unique
        }))
    
    return col_info


def _is_int(s: str) -> bool:
    try:
        int(s.replace(",", "").strip())
        return True
    except ValueError:
        return False


def _is_float(s: str) -> bool:
    try:
        float(s.replace(",", "").replace("%", "").replace("$", "").strip())
        return True
    except ValueError:
        return False


def _check_sequential(nums: List[int]) -> Optional[int]:
    """检查数值序列是否等差，返回步长（0=非常数步长）"""
    if len(nums) < 3:
        return None
    diffs = [nums[i+1] - nums[i] for i in range(min(10, len(nums)-1))]
    if all(d == diffs[0] for d in diffs):
        return diffs[0]
    return None


def _optimal_decimals(nums: List[float]) -> int:
    """确定最优小数位数（保留2位有效精度）"""
    if not nums:
        return 2
    # 找最小的非零差异
    sorted_nums = sorted(nums)
    min_diff = min(abs(sorted_nums[i+1] - sorted_nums[i]) for i in range(len(sorted_nums)-1) if sorted_nums[i+1] != sorted_nums[i])
    if min_diff == 0 or math.isinf(min_diff):
        return 2
    decimals = max(0, -int(math.floor(math.log10(min_diff))) + 1)
    return min(decimals, 4)  # 最多保留4位


# ── 数据紧凑化 ──────────────────────────────────

def compact_data(headers: List[str], rows: List[List[str]], 
                 col_info: List[Tuple]) -> Tuple[str, str, List[str]]:
    """
    对数据进行紧凑化编码。
    
    返回: (compact_text_header, compact_text_body, legend_lines)
    - compact_text_header: 紧凑列名(长度≤4)
    - compact_text_body: 紧凑数据行列表
    - legend_lines: 每列的编码说明
    """
    n_cols = len(headers)
    
    # 生成短列名
    short_names = []
    col_legends = []
    for ci, (name, ctype, meta) in enumerate(col_info):
        # 短名：C0, C1, C2...
        short = f"C{ci}"
        short_names.append(short)
        
        # 图例说明
        if ctype == ColumnType.BOOL:
            col_legends.append(f"{short}={name} [{meta['key0']}→0, {meta['key1']}→1]")
        elif ctype == ColumnType.CATEGORY:
            map_str = ", ".join(f"{k}→{c}" for k, c in meta['map'].items())
            col_legends.append(f"{short}={name} [{map_str}]")
        elif ctype == ColumnType.ID:
            col_legends.append(f"{short}={name} [delta, start={meta['start']}, step={meta['step']}]")
        elif ctype == ColumnType.CONST:
            col_legends.append(f"{short}={name} [const={meta['value']}]")
        elif ctype == ColumnType.FLOAT:
            col_legends.append(f"{short}={name} [{meta['decimals']}dec, {meta['min']}-{meta['max']}]")
        elif ctype == ColumnType.INT:
            col_legends.append(f"{short}={name} [int, {meta['min']}-{meta['max']}]")
        else:
            col_legends.append(f"{short}={name}")
    
    legend = " | ".join(col_legends)
    
    # 紧凑数据体
    compact_rows = []
    for ri, row in enumerate(rows):
        compact_vals = []
        for ci in range(n_cols):
            raw = row[ci].strip() if ci < len(row) else ""
            ctype = col_info[ci][1]
            meta = col_info[ci][2]
            
            compact_vals.append(_compact_value(raw, ctype, meta, ri))
        compact_rows.append("\t".join(compact_vals))
    
    compact_header = "\t".join(short_names)
    
    return compact_header, compact_rows, [legend]


def _compact_value(raw: str, ctype: str, meta: dict, row_idx: int) -> str:
    """单值紧凑化"""
    if not raw:
        return "-"
    
    if ctype == ColumnType.CONST:
        return ""
    
    if ctype == ColumnType.BOOL:
        return meta['mapping'].get(raw, "?")
    
    if ctype == ColumnType.CATEGORY:
        return meta['map'].get(raw, "?")
    
    if ctype == ColumnType.ID:
        if meta.get('format') == 'delta' and row_idx == 0:
            return str(meta['start'])
        elif meta.get('format') == 'delta':
            # 计算差值
            actual = int(raw)
            expected = meta['start'] + row_idx * meta['step']
            delta = actual - expected
            if delta == 0:
                return "."
            return f"+{delta}" if delta > 0 else str(delta)
        return raw
    
    if ctype == ColumnType.FLOAT:
        try:
            f = float(raw.replace(",", "").replace("%", "").replace("$", ""))
            decimals = meta.get('decimals', 2)
            return f"{f:.{decimals}f}"
        except ValueError:
            return raw
    
    if ctype == ColumnType.INT:
        return raw  # 整数已经是紧凑的
    
    # TEXT：裁剪超长文本
    max_len = meta.get('max_len', 20)
    if len(raw) > 12:
        return raw[:10] + ".."
    return raw


# ── 去格式冗余 ──────────────────────────────────

def strip_csv_formatting(filepath: str, output_path: Optional[str] = None) -> Tuple[List[str], List[List[str]]]:
    """去除CSV格式冗余，返回纯数据"""
    with open(filepath, "r", encoding="utf-8-sig") as f:
        content = f.read()
    
    # 最简CSV解析（不处理引号转义，只取逗号分隔）
    lines = content.strip().split("\n")
    if not lines:
        return [], []
    
    parsed = []
    for line in lines:
        # 去除引号包裹
        parts = []
        for cell in line.split(","):
            cell = cell.strip().strip('"').strip("'")
            parts.append(cell)
        parsed.append(parts)
    
    if not parsed:
        return [], []
    
    headers = parsed[0]
    rows = parsed[1:] if len(parsed) > 1 else []
    
    if output_path:
        # 写出无格式版本（Tab分隔）
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\t".join(headers) + "\n")
            for row in rows:
                f.write("\t".join(row) + "\n")
    
    return headers, rows


# ── 主流程 ──────────────────────────────────────

def compact_file(filepath: str, output_dir: str = "output", 
                 sheet: Optional[str] = None) -> Tuple[List[str], List[List[str]], str]:
    """完整紧凑化流程"""
    # 1. 读取
    from data_encoder import read_data
    headers, rows = read_data(filepath, sheet)
    
    print(f"📖 原始数据: {len(headers)}列 × {len(rows)}行")
    
    # 2. 类型推断
    col_info = infer_column_types(headers, rows)
    n_dict = sum(1 for _, t, _ in col_info if t == ColumnType.CATEGORY)
    n_id = sum(1 for _, t, _ in col_info if t == ColumnType.ID)
    n_const = sum(1 for _, t, _ in col_info if t == ColumnType.CONST)
    print(f"🔍 类型: {n_dict}字典 {n_id}差值 {n_const}常数 "
          f"{sum(1 for _,t,_ in col_info if t==ColumnType.FLOAT)}浮点 "
          f"{sum(1 for _,t,_ in col_info if t==ColumnType.INT)}整数")
    
    # 3. 紧凑化
    compact_h, compact_rows, legends = compact_data(headers, rows, col_info)
    print(f"📦 紧凑后: {len(compact_rows)}行, 列名{len(compact_h)}→{len(compact_h.split(chr(9)))}短码")
    
    # 4. 输出紧凑文件
    os.makedirs(output_dir, exist_ok=True)
    base = Path(filepath).stem
    out_path = os.path.join(output_dir, f"{base}_compact.txt")
    
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# " + legends[0] + "\n")
        f.write(compact_h + "\n")
        for row in compact_rows:
            f.write(row + "\n")
    
    print(f"✅ 紧凑文件: {out_path}")
    stats = os.path.getsize(out_path)
    orig = os.path.getsize(filepath)
    print(f"   压缩: {stats:,}字节 vs {orig:,}字节 ({stats/orig*100:.0f}%)")
    
    return headers, rows, out_path


def main():
    parser = argparse.ArgumentParser(description="数据紧凑化预处理器")
    parser.add_argument("input", help="输入文件 (CSV/Excel)")
    parser.add_argument("-o", "--output", default="output", help="输出目录")
    parser.add_argument("--sheet", default=None, help="Excel工作表")
    parser.add_argument("--to-csv", action="store_true", help="输出纯净CSV(仅去格式)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"❌ 文件不存在: {args.input}")
        return 1
    
    if args.to_csv:
        clean_path = os.path.join(args.output, Path(args.input).name.replace(".csv", "_clean.csv"))
        os.makedirs(args.output, exist_ok=True)
        strip_csv_formatting(args.input, clean_path)
        orig = os.path.getsize(args.input)
        clean = os.path.getsize(clean_path)
        print(f"✅ 去格式完成: {clean:,}字节 (原{orig:,}, {clean/orig*100:.0f}%)")
        return 0
    
    compact_file(args.input, args.output, args.sheet)
    return 0


if __name__ == "__main__":
    main()
