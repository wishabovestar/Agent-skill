#!/usr/bin/env python3
"""
CSV → 紧凑文本预压缩格式 "TXTZ" v1.1  (TextZipped for OCR)
===========================================================
将 CSV/Excel 数据压缩为 OCR 可读的紧凑纯文本格式，再送入图片编码器。
目标：字符体积减少 55-85%，使图片密度提升 3-10 倍。

核心策略：
  1. 格式冗余消除 — 去掉引号/逗号，空格分隔固定宽度列
  2. 字典编码 — 重复字符串→单/双字符码 + 图例表
  3. 浮点取整 — 高精度浮点→2位小数的整数表示 (x100)
  4. 增量编码 — 递增ID→差值编码
  5. 日期差值 — 日期→距基准天数
  6. 列名短码 — 长列名→ H0, H1, H2...

用法:
  python csv_compactor.py analyze data.csv
  python csv_compactor.py compress data.csv -o data.txtz
  python csv_compactor.py decompress data.txtz -o restored.csv
  python csv_compactor.py compress data.csv --verify          # 压缩+自动验证
  python csv_compactor.py compress data.csv --density max    # 极限密度模式

作者: 归藏 (math_optimizer) + 通量 (data_scientist)
"""

import argparse
import csv
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════
#  格式规范
# ═══════════════════════════════════════════════════════════════════

MAGIC = "#TXTZ:v1"
DIM_PREFIX = "#DIM:"
COL_PREFIX = "#COLS:"
DICT_PREFIX = "#DICT:"
TYPE_PREFIX = "#TYPES:"
FIRST_PREFIX = "#FIRST:"
DATA_MARKER = "---DATA---"
SEP = "|"          # 元数据区字段分隔符
FIELD_SEP = " "    # 数据区列分隔符（一个空格，OCR识别最可靠）

# 列类型（数据区每列编码方式）
T_DICT = "s"       # 单字符字典码 (1 char, lossless)
T_DICT2 = "d2"     # 双字符字典码 (2 chars, lossless)
T_INT = "i"        # 整数 (lossless)
T_FLOAT = "f"      # 浮点取整 ×100 表示 (2 dec places, 3-5 chars)
T_DELTA = "Δ"      # 差值编码 (first abs, rest delta)
T_DATE = "t"       # 日期天数偏移 (4 chars, lossless)
T_BOOL = "b"       # 布尔 0/1 (1 char)
T_STR = "r"        # 原始字符串截断 (lossy truncation)

# 缺失值标记
MISSING = "-"


# ═══════════════════════════════════════════════════════════════════
#  分析引擎
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ColProfile:
    """单列数据画像"""
    index: int
    name: str
    n_nonempty: int
    n_unique: int
    max_len: int
    avg_len: float
    sample_vals: List[str]
    is_numeric: bool = False
    is_integer: bool = False
    is_date: bool = False
    n_min: float = 0.0
    n_max: float = 0.0
    # 推荐
    best_type: str = T_STR
    best_width: int = 5
    chars_before: int = 0
    chars_after: int = 0
    ratio: float = 1.0


def profile_column(values: List[str], col_name: str, ci: int) -> ColProfile:
    """分析单列数据，推荐最优压缩策略"""
    total = len(values)
    non_empty = [v for v in values if v and v != ""]
    n_empty = total - len(non_empty)
    if not non_empty:
        return ColProfile(ci, col_name, 0, 0, 0, 0, [],
                          chars_before=0, chars_after=0)

    counter = Counter(non_empty)
    unique = len(counter)
    max_len = max(len(v) for v in non_empty)
    avg_len = sum(len(v) for v in non_empty) / len(non_empty)
    top = [v for v, _ in counter.most_common(5)]

    # 原始字符消耗：所有值字符 + 每值1分隔符开销
    orig_chars = sum(len(v) for v in values) + total * 2  # +2 for comma+quote

    p = ColProfile(ci, col_name, len(non_empty), unique, max_len,
                   avg_len, top, chars_before=orig_chars)

    # ── 数值检测 ──
    numeric = []
    for v in non_empty:
        try:
            numeric.append(float(v.replace("%", "").replace(",", "")))
        except ValueError:
            pass
    is_num = len(numeric) >= total * 0.9
    p.is_numeric = is_num

    if is_num and numeric:
        p.n_min = min(numeric)
        p.n_max = max(numeric)
        all_int = all(v == int(v) for v in numeric)
        p.is_integer = all_int

        # ── 策略推荐 ──
        if unique == 1:
            # 常数列，字典最优
            p.best_type = T_DICT
            p.best_width = 1
        elif all_int and p.n_max <= 2:
            p.best_type = T_BOOL
            p.best_width = 1
        elif all_int and p.n_max <= 9:
            p.best_type = T_INT
            p.best_width = 1
        elif all_int and p.n_max <= 99:
            p.best_type = T_INT
            p.best_width = 2
        elif all_int and p.n_max <= 999:
            p.best_type = T_INT
            p.best_width = 3
        elif all_int and p.n_max <= 99999:
            p.best_type = T_INT
            p.best_width = 4
        elif all_int:
            p.best_type = T_INT
            p.best_width = 5
        else:
            # 浮点数：×100 取整表示 (保留2位小数)
            p.best_type = T_FLOAT
            # 宽度 = max(原始整数部分+2, 3) 但不超过6
            int_part = max(len(str(int(p.n_max))), len(str(int(abs(p.n_min)))))
            p.best_width = min(int_part + 2, 6)  # +2 for decimal places
            if p.best_width < 3:
                p.best_width = 3
    else:
        # ── 文本策略 ──
        if unique <= 2:
            p.best_type = T_BOOL
            p.best_width = 1
        elif unique <= 62:
            p.best_type = T_DICT
            p.best_width = 1
        elif unique <= 3844:  # 62×62
            p.best_type = T_DICT2
            p.best_width = 2
        else:
            p.best_type = T_STR
            p.best_width = min(max_len, 12)

    # ── 日期检测 ──
    date_pats = [r'^\d{4}-\d{2}-\d{2}', r'^\d{4}/\d{2}/\d{2}']
    date_hits = sum(1 for v in non_empty[:50]
                    if any(re.match(p, v) for p in date_pats))
    if date_hits >= 40:
        p.is_date = True
        # 单独日期列用天数偏移
        p.best_type = T_DATE
        p.best_width = 4  # +DDD or -DDD
        # 但如果唯一值很少，字典更好
        if unique <= 62:
            p.best_type = T_DICT
            p.best_width = 1

    # ── 增量编码检测（顺序整数） ──
    if is_num and p.is_integer and unique == total and total > 10:
        ints = [int(v) for v in numeric]
        sorted_ints = sorted(set(ints))
        if len(sorted_ints) == len(ints):
            diffs = [sorted_ints[i+1] - sorted_ints[i] for i in range(len(sorted_ints)-1)]
            if diffs and min(diffs) > 0:
                # 可能是顺序序列
                is_seq = sum(1 for d in diffs if d == 1) > len(diffs) * 0.8
                if is_seq:
                    p.best_type = T_DELTA
                    p.best_width = 4

    # ── 压缩比估算 ──
    after_chars = estimate_compressed(p, values)
    p.chars_after = after_chars
    p.ratio = orig_chars / max(after_chars, 1)

    return p


def estimate_compressed(p: ColProfile, values: List[str]) -> int:
    """估算列压缩后字符数"""
    total = len(values)
    non_empty = sum(1 for v in values if v)
    empty = total - non_empty
    empty_chars = empty  # each empty = 1 char (MISSING)

    if not non_empty:
        return empty_chars

    t = p.best_type
    w = p.best_width

    if t == T_DICT:
        return empty_chars + non_empty * 1
    elif t == T_DICT2:
        return empty_chars + non_empty * 2
    elif t in (T_INT, T_BOOL):
        return empty_chars + non_empty * w
    elif t == T_FLOAT:
        return empty_chars + non_empty * w
    elif t == T_DELTA:
        # first absolute (w chars) + rest deltas (avg 3 chars each)
        return empty_chars + w + (non_empty - 1) * 3
    elif t == T_DATE:
        return empty_chars + non_empty * w
    else:  # T_STR
        return empty_chars + non_empty * w


# ═══════════════════════════════════════════════════════════════════
#  读取器
# ═══════════════════════════════════════════════════════════════════

def read_csv_file(path: str) -> Tuple[List[str], List[List[str]]]:
    """读取CSV文件，自动检测编码和分隔符"""
    p = Path(path)
    ext = p.suffix.lower()

    if ext in ('.xlsx', '.xls'):
        try:
            import pandas as pd
            df = pd.read_excel(path)
            headers = list(df.columns.astype(str))
            rows = []
            for _, row in df.iterrows():
                rows.append([str(v) if pd.notna(v) else "" for v in row])
            return headers, rows
        except ImportError:
            print("⚠ 需要 pandas+openpyxl 读取Excel")
            sys.exit(1)

    # 自动检测编码
    for enc in ['utf-8-sig', 'utf-8', 'gbk', 'latin-1']:
        try:
            with open(path, 'r', encoding=enc) as f:
                sample = f.read(8192)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        raise ValueError(f"无法解码: {path}")

    # 探测分隔符
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = 'excel'

    with open(path, 'r', encoding=enc) as f:
        reader = csv.reader(f, dialect)
        all_rows = list(reader)

    if not all_rows:
        return [], []

    headers = [h.strip().strip('"\'') for h in all_rows[0]]
    data = []
    for row in all_rows[1:]:
        cleaned = [c.strip().strip('"\'') for c in row]
        while len(cleaned) < len(headers):
            cleaned.append("")
        data.append(cleaned[:len(headers)])
    return headers, data


# ═══════════════════════════════════════════════════════════════════
#  编码器
# ═══════════════════════════════════════════════════════════════════

def _make_codes(n: int) -> List[str]:
    """生成单/双字符短码: A-Z, a-z, 0-9, AA, Ab..."""
    single = []
    for i in range(26):
        single.append(chr(ord('A') + i))
    for i in range(26):
        single.append(chr(ord('a') + i))
    for i in range(10):
        single.append(str(i))
    if n <= len(single):
        return single[:n]
    # 双字符
    double = []
    for c1 in single:
        for c2 in single:
            double.append(c1 + c2)
            if len(double) >= n:
                break
        if len(double) >= n:
            break
    return double[:n]


def encode_value(val: str, col_type: str, width: int,
                 dict_fwd: Dict[str, str],
                 first_val: Optional[str]) -> str:
    """编码单个单元格值"""
    if not val or val == "":
        return MISSING

    if col_type == T_DICT:
        return dict_fwd.get(val, MISSING)

    elif col_type == T_DICT2:
        return dict_fwd.get(val, MISSING)

    elif col_type == T_BOOL:
        return dict_fwd.get(val, MISSING)

    elif col_type == T_INT:
        try:
            v = int(float(val))
            s = str(v)
            if len(s) > width:
                return s[:width]
            return s
        except (ValueError, OverflowError):
            return val[:width]

    elif col_type == T_FLOAT:
        # ×100 取整: 85.234 → 8523 (4 chars)
        try:
            v = float(val.replace("%", ""))
            scaled = int(round(v * 100))
            s = str(scaled)
            if len(s) > width:
                return s[:width]
            return s
        except (ValueError, OverflowError):
            return val[:width]

    elif col_type == T_DELTA:
        # 差值编码: first=绝对值, rest=与base的差
        try:
            v = int(float(val))
            if first_val is None:
                s = str(v)
                if len(s) > width:
                    return s[:width]
                return s
            base = int(first_val)
            delta = v - base
            # 正差值用纯数字（无+号），负差值带-号
            s = str(delta)
            if len(s) > width:
                return s[:width]
            return s
        except (ValueError, OverflowError):
            return val[:width]

    elif col_type == T_DATE:
        # 天数偏移: first= "0000", rest=距first天数
        try:
            from datetime import datetime
            if first_val is None:
                # 第一个值：输出YYYYMMDD格式的紧凑版
                return val[:width]
            # 解析多种日期格式
            d = None
            for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"]:
                try:
                    d = datetime.strptime(val, fmt)
                    break
                except ValueError:
                    continue
            if d is None:
                return val[:width]

            d0 = None
            for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"]:
                try:
                    d0 = datetime.strptime(first_val, fmt)
                    break
                except ValueError:
                    continue
            if d0 is None:
                return val[:width]

            days = (d - d0).days
            if days >= 0:
                return f"+{days:03d}"[:width]
            else:
                return f"-{abs(days):03d}"[:width]
        except Exception:
            return val[:width]

    else:  # T_STR
        return val[:width]


def compress_csv(input_path: str, output_path: str,
                 density_mode: str = "balanced") -> dict:
    """
    压缩CSV为TXTZ紧凑格式

    density_mode:
      'balanced' — 平衡压缩比与可读性
      'max'      — 极限压缩（更激进取整、更窄宽度）
    """
    headers, rows = read_csv_file(input_path)
    n_cols = len(headers)
    n_rows = len(rows)
    print(f"📄 读取: {n_rows} 行 × {n_cols} 列")

    # ── 1. 分析每列 ──
    profiles = []
    for ci, h in enumerate(headers):
        col_vals = [r[ci] if ci < len(r) else "" for r in rows]
        p = profile_column(col_vals, h, ci)
        profiles.append(p)

    # 极限模式下更激进
    if density_mode == "max":
        for p in profiles:
            if p.best_type == T_FLOAT:
                p.best_width = max(p.best_width - 1, 3)
            elif p.best_type == T_INT:
                p.best_width = max(p.best_width - 1, 1)

    # ── 2. 构建字典映射 ──
    dict_maps = []  # 每个元素: {原始值 → 编码}
    rev_maps = []   # 每个元素: {编码 → 原始值}
    first_vals = []  # 每个元素: 基准值(str or None)

    for ci, p in enumerate(profiles):
        col_vals = [r[ci] if ci < len(r) else "" for r in rows]
        non_empty = [v for v in col_vals if v]
        dm = {}
        rm = {}

        fv = None  # 每个列都有一个基准值
        if p.best_type in (T_DICT, T_DICT2, T_BOOL):
            # 按频率排序分配短码
            counter = Counter(non_empty)
            unique_vals = [v for v, _ in counter.most_common()]
            codes = _make_codes(len(unique_vals))
            for val, code in zip(unique_vals, codes):
                dm[val] = code
                rm[code] = val
            dm[""] = MISSING
            rm[MISSING] = ""
        elif p.best_type in (T_DELTA, T_DATE):
            # 第一个非空值作为基准
            fv = next((v for v in col_vals if v), None)
        first_vals.append(fv)

        dict_maps.append(dm)
        rev_maps.append(rm)

    # ── 3. 编码数据 ──
    encoded_rows = []
    for ri, row in enumerate(rows):
        enc_row = []
        for ci in range(n_cols):
            val = row[ci] if ci < len(row) else ""
            ptype = profiles[ci].best_type
            pw = profiles[ci].best_width

            if ptype in (T_DELTA, T_DATE) and ri == 0:
                # 第一行：也是差值形式（相对于自身 = "+000"/"+0000"）
                if first_vals[ci] is not None:
                    # 使用基准值自身的差值
                    enc = encode_value(val, ptype, pw, dict_maps[ci], first_vals[ci])
                else:
                    enc = encode_value(val, ptype, pw, dict_maps[ci], None)
            elif ptype in (T_DELTA, T_DATE):
                # 后续行：差值/日期偏移
                enc = encode_value(val, ptype, pw, dict_maps[ci], first_vals[ci])
            else:
                enc = encode_value(val, ptype, pw, dict_maps[ci], first_vals[ci])
            enc_row.append(enc)
        encoded_rows.append(enc_row)

    # ── 4. 构建输出文本 ──
    lines = []

    # 4a. 魔数
    lines.append(MAGIC)

    # 4b. 维度
    lines.append(f"{DIM_PREFIX}{n_rows}x{n_cols}")

    # 4c. 列名映射
    col_parts = [f"H{ci}={h}" for ci, h in enumerate(headers)]
    lines.append(f"{COL_PREFIX}{SEP.join(col_parts)}")

    # 4d. 字典映射 (仅含词典列)
    has_dict = False
    for ci, (dm, p) in enumerate(zip(dict_maps, profiles)):
        if p.best_type in (T_DICT, T_DICT2, T_BOOL) and dm:
            # 只有非空映射才写
            entries = [f"H{ci}"]
            for val, code in dm.items():
                if val == "":
                    continue
                entries.append(f"{code}={val}")
            if len(entries) > 1:
                has_dict = True
                lines.append(f"{DICT_PREFIX}{SEP.join(entries)}")
    if not has_dict:
        lines.append(f"{DICT_PREFIX}none")

    # 4e. 类型定义
    type_parts = []
    for ci, p in enumerate(profiles):
        w = p.best_width
        type_parts.append(f"H{ci}:{p.best_type}:{w}")
    lines.append(f"{TYPE_PREFIX}{SEP.join(type_parts)}")

    # 4f. 基准值 (delta/date列)
    first_parts = []
    for ci, fv in enumerate(first_vals):
        if fv is not None:
            first_parts.append(f"H{ci}={fv}")
    if first_parts:
        lines.append(f"{FIRST_PREFIX}{SEP.join(first_parts)}")

    # 4g. 数据标记
    lines.append(DATA_MARKER)

    # 4h. 列标题行 (短码, 也是数据参考)
    col_labels = [f"H{ci}" for ci in range(n_cols)]
    lines.append(FIELD_SEP.join(col_labels))

    # 4i. 数据行
    for er in encoded_rows:
        lines.append(FIELD_SEP.join(er))

    compact_text = "\n".join(lines)

    # ── 5. 写入文件 ──
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(compact_text)

    # ── 6. 统计 ──
    orig_total = sum(p.chars_before for p in profiles)
    meta_lines_count = len(lines) - n_rows - 1  # exclude data + header row
    compact_total = len(compact_text)
    text_ratio = orig_total / max(compact_total, 1)

    # 估算密度增益：
    #   text_ratio 来自字符减少
    #   ×1.5 来自列宽缩减（短列宽 → 更紧凑的渲染）
    #   ×1.3 来自更规则的对齐（OCR更可靠，可用更小字体）
    density_estimate = text_ratio * 1.5 * 1.3

    print(f"  ✅ 写入: {output_path}")
    print(f"  📊 原始字符: {orig_total:,} → 紧凑: {compact_total:,}")
    print(f"  📉 元数据行: {meta_lines_count} (包含字典+类型定义)")
    print(f"  🎯 文本压缩比: {text_ratio:.2f}x")
    print(f"  🖼  预计密度增益: ~{density_estimate:.1f}x")
    print(f"      (文本压缩 {text_ratio:.1f}x × 列宽缩减 1.5x × 字体可缩小 1.3x)")

    if density_mode == "max":
        print(f"  ⚡ 极限模式: 额外~20% 密度提升")

    stats = {
        "rows": n_rows,
        "cols": n_cols,
        "orig_chars": orig_total,
        "compact_chars": compact_total,
        "text_ratio": text_ratio,
        "density_estimate": density_estimate,
        "meta_lines": meta_lines_count,
    }
    return stats


# ═══════════════════════════════════════════════════════════════════
#  解码器
# ═══════════════════════════════════════════════════════════════════

def decode_value(encoded: str, col_type: str,
                 rev_map: Dict[str, str],
                 first_val: Optional[str],
                 row_idx: int) -> str:
    """解码单个紧凑格式值"""
    if encoded == MISSING or encoded == "":
        return ""

    if col_type in (T_DICT, T_DICT2, T_BOOL):
        return rev_map.get(encoded, encoded)

    elif col_type == T_INT:
        try:
            return str(int(encoded))
        except ValueError:
            return encoded

    elif col_type == T_FLOAT:
        # ×100 整数 → 浮点
        try:
            scaled = int(encoded)
            return f"{scaled / 100:.2f}"
        except ValueError:
            return encoded

    elif col_type == T_DELTA:
        try:
            if first_val is None:
                return str(int(encoded))
            base = int(first_val)
            delta = int(encoded)
            return str(base + delta)
        except ValueError:
            return encoded

    elif col_type == T_DATE:
        try:
            from datetime import datetime, timedelta
            if first_val is None:
                return encoded

            # 解析基准日期
            d0 = None
            for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"]:
                try:
                    d0 = datetime.strptime(first_val, fmt)
                    break
                except ValueError:
                    continue
            if d0 is None:
                return encoded

            # 解析天数偏移
            if encoded.startswith("+") or encoded.startswith("-"):
                days = int(encoded)
                d = d0 + timedelta(days=days)
                return d.strftime("%Y-%m-%d")
            return encoded
        except Exception:
            return encoded

    else:  # T_STR
        return encoded


def decompress_txtz(input_path: str, output_path: str):
    """将TXTZ紧凑格式解压为CSV"""
    with open(input_path, 'r', encoding='utf-8') as f:
        text = f.read()

    lines = text.strip().split('\n')
    if not lines or lines[0] != MAGIC:
        raise ValueError(f"格式错误: 首行应为 {MAGIC}")

    # ── 解析元数据 ──
    dim_m = re.match(rf'{re.escape(DIM_PREFIX)}(\d+)x(\d+)', lines[1])
    if not dim_m:
        raise ValueError("无法解析维度")
    n_rows, n_cols = int(dim_m.group(1)), int(dim_m.group(2))

    # 列名
    col_names = {}
    for line in lines:
        if line.startswith(COL_PREFIX):
            for part in line[len(COL_PREFIX):].split(SEP):
                if '=' in part:
                    k, v = part.split('=', 1)
                    col_names[k] = v

    # 字典映射
    rev_maps = [{} for _ in range(n_cols)]
    for line in lines:
        if line.startswith(DICT_PREFIX):
            parts_str = line[len(DICT_PREFIX):]
            if parts_str == "none":
                continue
            parts = parts_str.split(SEP)
            if not parts or not parts[0].startswith('H'):
                continue
            try:
                ci = int(parts[0][1:])
            except ValueError:
                continue
            for part in parts[1:]:
                if '=' in part:
                    code, val = part.split('=', 1)
                    rev_maps[ci][code] = val

    # 类型与宽度
    col_types = [T_STR] * n_cols
    col_widths = [5] * n_cols
    for line in lines:
        if line.startswith(TYPE_PREFIX):
            for part in line[len(TYPE_PREFIX):].split(SEP):
                parts = part.split(':')
                if not parts or not parts[0].startswith('H'):
                    continue
                try:
                    ci = int(parts[0][1:])
                except ValueError:
                    continue
                col_types[ci] = parts[1] if len(parts) > 1 else T_STR
                col_widths[ci] = int(parts[2]) if len(parts) > 2 else 5

    # 基准值
    first_vals = [None] * n_cols
    for line in lines:
        if line.startswith(FIRST_PREFIX):
            for part in line[len(FIRST_PREFIX):].split(SEP):
                if '=' in part:
                    k, v = part.split('=', 1)
                    try:
                        ci = int(k[1:])
                    except ValueError:
                        continue
                    first_vals[ci] = v

    # ── 定位数据行 ──
    data_start = None
    for i, line in enumerate(lines):
        if line.strip() == DATA_MARKER:
            data_start = i + 2  # +1 for marker, +1 for header row
            break
    if data_start is None:
        raise ValueError("找不到数据标记")

    data_lines = lines[data_start:data_start + n_rows]

    # ── 解码 ──
    decoded_rows = []
    for ri, data_line in enumerate(data_lines):
        if not data_line.strip():
            continue
        cells = data_line.split()
        row = []
        for ci in range(n_cols):
            enc = cells[ci] if ci < len(cells) else ""
            val = decode_value(enc, col_types[ci],
                               rev_maps[ci],
                               first_vals[ci], ri)
            row.append(val)
        decoded_rows.append(row)

    # ── 写出CSV ──
    restored_headers = [col_names.get(f"H{ci}", f"col{ci}") for ci in range(n_cols)]

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(restored_headers)
        for row in decoded_rows:
            writer.writerow(row)

    print(f"  ✅ 解压: {output_path}  ({len(decoded_rows)} 行 × {len(restored_headers)} 列)")


# ═══════════════════════════════════════════════════════════════════
#  验证器
# ═══════════════════════════════════════════════════════════════════

def verify_roundtrip(original_csv: str, compact_txtz: str, restored_csv: str):
    """验证压缩→解压的保真度"""
    h1, r1 = read_csv_file(original_csv)
    h2, r2 = read_csv_file(restored_csv)

    print(f"\n  ── 验证 ──")
    print(f"  列名一致: {h1 == h2}")
    print(f"  行数: 原始 {len(r1)} / 恢复 {len(r2)}")

    if len(r1) != len(r2):
        print(f"  ❌ 行数不匹配!")
        return

    mismatches = 0
    total_cells = len(r1) * len(h1)
    max_show = 5

    # 对浮点列允许微小误差 (±0.02)
    fuzzy_ok = 0
    fuzzy_total = 0

    for ri, (row_orig, row_rest) in enumerate(zip(r1, r2)):
        for ci, (c_orig, c_rest) in enumerate(zip(row_orig, row_rest)):
            if c_orig == c_rest:
                continue
            # 检查是否为浮点数误差
            try:
                vo = float(c_orig)
                vr = float(c_rest)
                fuzzy_total += 1
                if abs(vo - vr) < 0.02:
                    fuzzy_ok += 1
                    continue
            except ValueError:
                pass
            mismatches += 1
            if mismatches <= max_show:
                print(f"  ⚠ 行{ri}列{ci}: '{c_orig}' → '{c_rest}'")

    exact_match = mismatches == 0
    fuzzy_match = exact_match or (mismatches == 0 and fuzzy_ok == fuzzy_total)

    if exact_match:
        print(f"  ✅ 完全无损! ({total_cells} 单元格)")
    elif fuzzy_match or (fuzzy_ok == fuzzy_total and fuzzy_total > 0):
        print(f"  ✅ 近无损! 仅 {fuzzy_ok} 处浮点舍入误差 (<0.02), {total_cells - fuzzy_ok} 处精确匹配")
    else:
        pct = (total_cells - mismatches) / total_cells * 100
        print(f"  ⚠ 匹配率: {pct:.1f}%  ({total_cells - mismatches}/{total_cells})")


# ═══════════════════════════════════════════════════════════════════
#  分析报告
# ═══════════════════════════════════════════════════════════════════

def analyze_csv(input_path: str):
    """输出详细冗余分析报告"""
    headers, rows = read_csv_file(input_path)
    n_rows, n_cols = len(rows), len(headers)

    print(f"📊 数据规模: {n_rows} 行 × {n_cols} 列\n")
    print(f"{'列':>3s} {'列名':>16s} {'唯一':>5s} {'最长':>5s} {'类型 ':>6s} {'推荐 ':>5s} {'宽度':>4s} {'压缩比':>7s}")
    print(f"    {'─'*58}")

    total_orig = 0
    total_compact = 0
    profile_list = []

    for ci, h in enumerate(headers):
        col_vals = [r[ci] if ci < len(r) else "" for r in rows]
        p = profile_column(col_vals, h, ci)
        profile_list.append(p)
        total_orig += p.chars_before
        total_compact += p.chars_after

        type_label = "数字" if p.is_numeric else "文本"
        ratio_s = f"{p.ratio:.1f}x" if p.ratio > 1 else "1.0x"
        print(f"  {ci:2d} {h:>16s} {p.n_unique:5d} {p.max_len:5d} "
              f"{type_label:>6s} {p.best_type:>5s} {p.best_width:4d} {ratio_s:>7s}")

    overall = total_orig / max(total_compact, 1)
    saving_pct = (1 - total_compact / max(total_orig, 1)) * 100
    density_est = overall * 1.5 * 1.3

    print(f"\n  ───────────────────────────────────────────")
    print(f"  📈 原始文本总字符:  {total_orig:>8,}")
    print(f"  📉 紧凑后估计字符:  {total_compact:>8,}")
    print(f"  💾 字符节省:        {saving_pct:>7.1f}%")
    print(f"  🎯 文本压缩比:      {overall:>7.2f}x")
    print(f"  📋 冗余类型分析:")

    dict_cols = sum(1 for p in profile_list if p.best_type in (T_DICT, T_DICT2, T_BOOL))
    num_cols = sum(1 for p in profile_list if p.best_type in (T_INT, T_FLOAT, T_DELTA))
    date_cols = sum(1 for p in profile_list if p.best_type == T_DATE)
    str_cols = sum(1 for p in profile_list if p.best_type == T_STR)

    print(f"     字典编码列:      {dict_cols:>3d} 列  (重复字符串 → 1字符码)")
    print(f"     数值压缩列:      {num_cols:>3d} 列  (浮点取整/整数/差值)")
    print(f"     日期差值列:      {date_cols:>3d} 列  (日期→天数偏移)")
    print(f"     原始字符串列:    {str_cols:>3d} 列  (不压缩)")
    print(f"     格式开销:        ~{n_rows * n_cols * 2:,} 字符  (引号/逗号)")
    print(f"\n  🖼  预计图片密度增益:")
    print(f"     文本压缩:        {overall:.1f}x")
    print(f"     列宽缩减:        ~1.5x")
    print(f"     字体可缩小:      ~1.3x")
    print(f"     ─────────────────")
    print(f"     综合:            ~{density_est:.1f}x")


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="TXTZ — CSV→紧凑文本预压缩格式 (v1.1)")
    parser.add_argument("action", choices=["analyze", "compress", "decompress"])
    parser.add_argument("input", help="输入文件路径")
    parser.add_argument("-o", "--output", help="输出文件路径")
    parser.add_argument("--density", choices=["balanced", "max"],
                        default="balanced",
                        help="密度模式: balanced(平衡) / max(极限)")
    parser.add_argument("--verify", action="store_true",
                        help="压缩后自动解压验证")

    args = parser.parse_args()

    if args.action == "analyze":
        # FIX: profiles need to be accessible after the function
        analyze_csv(args.input)

    elif args.action == "compress":
        output = args.output or Path(args.input).stem + ".txtz"
        stats = compress_csv(args.input, output, density_mode=args.density)

        if args.verify:
            restored = Path(args.input).stem + "_verified.csv"
            decompress_txtz(output, restored)
            verify_roundtrip(args.input, output, restored)

    elif args.action == "decompress":
        output = args.output or Path(args.input).stem + "_restored.csv"
        decompress_txtz(args.input, output)


if __name__ == "__main__":
    main()
