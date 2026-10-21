#!/usr/bin/env python3
"""
数据文档→图片高鲁棒编码器 v1.0
=======================================
将 Excel/CSV 数据文档渲染为高鲁棒性图片，确保：
1. 压缩/截图/缩放后 OCR 仍可精确还原
2. 图片数量最少（数据密度最大化）
3. 后续 Agent 可通过 OCR 识别图片还原数据

配合数据处理流水线（data_processor.py）使用。

用法:
  python data_encoder.py data.csv -o output/
  python data_encoder.py data.xlsx -o output/ --sheet Sheet1
  python data_encoder.py data.csv -o output/ --split 500  # 每500行一张图
"""

import argparse
import csv
import os
import math
import textwrap
from pathlib import Path
from typing import List, Optional, Tuple, Union
from dataclasses import dataclass
from collections import defaultdict

import numpy as np

# ── 图片渲染引擎 ──────────────────────────────────
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


# ── 配置 ──────────────────────────────────────────

@dataclass
class RenderConfig:
    """渲染参数——平衡可读性与图片数量
    
    密度级别:
      'standard' (v1):  14pt   — 最高OCR精度, 低密度
      'dense'     (v2):   9pt   — 良好OCR精度, 高密度
      'ultra'     (v3):   7pt   — 极限密度, 需高DPI保证OCR
    """
    density: str = "dense"  # standard / dense / ultra
    
    def __post_init__(self):
        if self.density == "standard":
            self.font_size = 14
            self.header_font_size = 16
            self.cell_padding_x = 8
            self.cell_padding_y = 4
            self.border_width = 2
            self.header_border_width = 3
            self.dpi = 200
            self.max_image_width = 3000
        elif self.density == "dense":
            self.font_size = 8
            self.header_font_size = 10
            self.cell_padding_x = 2
            self.cell_padding_y = 1
            self.border_width = 1
            self.header_border_width = 1
            self.dpi = 200
            self.max_image_width = 4000
            self.max_image_height = 10000
        elif self.density == "ultra":
            self.font_size = 7
            self.header_font_size = 9
            self.cell_padding_x = 1
            self.cell_padding_y = 1
            self.border_width = 1
            self.header_border_width = 1
            self.dpi = 200
            self.max_image_width = 5000
            self.max_image_height = 12000
        
        self.font_name = "DejaVuSansMono"
        self.max_image_height = 10000
        self.image_format = "PNG"
        self.max_rows_per_image = 0
        self.max_cols_per_image = 16
    
    font_size: int = 8
    header_font_size: int = 10
    font_name: str = "DejaVuSansMono"
    cell_padding_x: int = 2
    cell_padding_y: int = 1
    border_width: int = 1
    header_border_width: int = 1
    bg_color: Tuple[int, ...] = (255, 255, 255)
    text_color: Tuple[int, ...] = (0, 0, 0)
    header_bg: Tuple[int, ...] = (220, 230, 241)
    header_text: Tuple[int, ...] = (0, 0, 0)
    border_color: Tuple[int, ...] = (0, 0, 0)
    alt_row_color: Tuple[int, ...] = (248, 248, 250)
    dpi: int = 200
    max_image_width: int = 4000
    max_image_height: int = 10000
    image_format: str = "PNG"
    max_rows_per_image: int = 0
    max_cols_per_image: int = 20


# ── 字体管理 ─────────────────────────────────────

def _get_font(config: RenderConfig, size: Optional[int] = None) -> ImageFont:
    """获取最佳可用字体（等宽优先）"""
    font_size = size or config.font_size
    candidates = [
        config.font_name,
        "Courier New",
        "Consolas",
        "LiberationMono",
        "DejaVu Sans Mono",
        "Arial",
        None,  # default
    ]
    for name in candidates:
        try:
            if name:
                return ImageFont.truetype(name, font_size)
            else:
                return ImageFont.load_default()
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


# ── 数据读取 ─────────────────────────────────────

def read_data(filepath: str, sheet: Optional[str] = None) -> Tuple[List[str], List[List[str]]]:
    """读取CSV/Excel/TXT，返回 (headers, rows)"""
    ext = Path(filepath).suffix.lower()
    
    if ext == ".csv":
        return _read_csv(filepath)
    elif ext in (".xlsx", ".xls"):
        return _read_excel(filepath, sheet)
    elif ext in (".txt", ".tsv"):
        return _read_tsv(filepath)
    elif ext in (".numbers",):
        return _read_csv(filepath.replace(".numbers", ".csv"))
    else:
        raise ValueError(f"不支持的文件格式: {ext}")


def _read_tsv(filepath: str) -> Tuple[List[str], List[List[str]]]:
    """读取Tab分隔的紧凑数据"""
    rows = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            rows.append(line.split("\t"))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def _read_csv(filepath: str) -> Tuple[List[str], List[List[str]]]:
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return [], []
    return rows[0], rows[1:]  # headers, data


def _read_excel(filepath: str, sheet: Optional[str] = None) -> Tuple[List[str], List[List[str]]]:
    if HAS_PANDAS:
        df = pd.read_excel(filepath, sheet_name=sheet)
        headers = list(df.columns)
        rows = []
        for _, row in df.iterrows():
            rows.append([str(v) if pd.notna(v) else "" for v in row])
        return headers, rows
    elif HAS_OPENPYXL:
        wb = openpyxl.load_workbook(filepath, read_only=True)
        ws = wb[sheet] if sheet else wb.active
        rows_data = list(ws.iter_rows(values_only=True))
        if not rows_data:
            return [], []
        headers = [str(c) if c is not None else "" for c in rows_data[0]]
        data = []
        for row in rows_data[1:]:
            data.append([str(c) if c is not None else "" for c in row])
        return headers, data
    else:
        raise ImportError("需要安装 pandas 或 openpyxl 以读取 Excel")


# ── 表格渲染（核心）───────────────────────────────

def render_table(headers: List[str], rows: List[List[str]], 
                 config: RenderConfig, title: Optional[str] = None,
                 col_offset: int = 0) -> Image.Image:
    """将二维数据渲染为高鲁棒性PNG图片"""
    font = _get_font(config)
    header_font = _get_font(config, config.header_font_size)
    title_font = _get_font(config, config.header_font_size + 4)
    
    # 智能数字格式化（减少字符宽度）
    formatted_rows = []
    for row in rows:
        frow = []
        for ci, val in enumerate(row):
            frow.append(_smart_format(val))
        formatted_rows.append(frow)
    rows = formatted_rows
    
    # 计算列宽
    n_cols = len(headers)
    col_widths = []
    for ci in range(n_cols):
        max_len = len(str(headers[ci])) if ci < len(headers) else 0
        for row in rows:
            if ci < len(row):
                max_len = max(max_len, len(str(row[ci])))
        char_w = config.font_size * 0.55
        pixel_w = int(max_len * char_w + config.cell_padding_x * 2)
        col_widths.append(max(pixel_w, 40))
    
    row_height = config.font_size * 1.4 + config.cell_padding_y * 2
    header_height = config.header_font_size * 1.4 + config.cell_padding_y * 2
    title_height = config.header_font_size * 2 + 15 if title else 0
    
    total_width = sum(col_widths) + config.border_width * (n_cols + 1) + 10
    total_width = min(int(total_width), config.max_image_width)
    
    n_rows = len(rows)
    total_height = (title_height + header_height + 
                    n_rows * row_height + 10)
    total_height = min(int(total_height), config.max_image_height)
    
    img = Image.new("RGB", (int(total_width), int(total_height)), config.bg_color)
    draw = ImageDraw.Draw(img)
    
    y = 5
    if title:
        draw.text((5, y), title, fill=config.text_color, font=title_font)
        y += title_height
    
    # 表头
    x = 5
    draw.rectangle([x, y, x + total_width - 5, y + header_height],
                   fill=config.header_bg, outline=config.border_color,
                   width=config.header_border_width)
    
    for ci, header in enumerate(headers):
        cx = x + config.border_width + sum(col_widths[:ci])
        if ci > 0:
            # 极细列分割线（点线效果 = 浅灰色细线）
            draw.line([(cx, y + 2), (cx, y + header_height - 2)],
                      fill=(180, 190, 200), width=1)
        draw.text((cx + config.cell_padding_x, y + config.cell_padding_y),
                  str(header), fill=config.header_text, font=header_font)
    
    y += header_height
    
    # 数据行（不加行背景，仅行间细线节省空间）
    for ri, row in enumerate(rows):
        # 仅每隔5行加行分隔线
        if ri > 0 and ri % 5 == 0:
            draw.line([(5, y), (total_width - 5, y)],
                      fill=(210, 210, 215), width=1)
        
        for ci in range(n_cols):
            cx = 5 + config.border_width + sum(col_widths[:ci])
            val = str(row[ci]) if ci < len(row) else ""
            is_number = _is_numeric(val)
            if is_number:
                text_w = len(val) * config.font_size * 0.55
                tx = cx + col_widths[ci] - config.cell_padding_x - int(text_w)
            else:
                tx = cx + config.cell_padding_x
            
            draw.text((tx, y + config.cell_padding_y), val,
                      fill=config.text_color, font=font)
        
        y += row_height
    
    return img


def _is_numeric(val: str) -> bool:
    if not val:
        return False
    v = val.replace(",", "").replace("-", "").replace(".", "").replace("%", "").replace("$", "")
    return v.isdigit()


def _smart_format(val: str) -> str:
    """智能格式化：减少冗余字符"""
    if not val or val == "nan" or val == "None":
        return ""
    v = val.strip()
    # 尝试压缩数字
    try:
        f = float(v.replace(",", "").replace("%", "").replace("$", "").replace(" ", ""))
        if abs(f) >= 10000:
            return f"{f:.0f}"
        elif abs(f) >= 100:
            return f"{f:.1f}"
        elif "." in v:
            # 保留2位有效数字
            return f"{f:.2f}"
        return v
    except ValueError:
        pass
    return v if len(v) <= 20 else v[:17] + ".."


def smart_split_table(headers: List[str], rows: List[List[str]], 
                      config: RenderConfig, 
                      base_name: str = "data") -> List[Tuple[str, Image.Image]]:
    """
    智能分割大表为多张图片。
    
    多栏布局：当列数较多时，在单张图片内并排渲染多组列，
    利用宽度换高度，减少图片总数。
    """
    images = []
    max_rows = config.max_rows_per_image
    n_cols = len(headers)
    
    if max_rows <= 0:
        row_h = config.font_size * 1.4 + config.cell_padding_y * 2
        header_h = config.header_font_size * 1.4 + config.cell_padding_y * 2
        # 预留40px边距+表头，估算每图最大行数
        max_rows = max(1, int((config.max_image_height - header_h - 30) / row_h))
    
    # 多栏布局策略：如果列数≤6，单栏；列数≤12，双栏；否则三栏
    n_panels = 1
    if n_cols > 12:
        n_panels = 3
    elif n_cols > 6:
        n_panels = 2
    
    # 每栏列数
    cols_per_panel = (n_cols + n_panels - 1) // n_panels
    
    # 生成所有行分块
    row_batches = []
    for ri in range(0, len(rows), max_rows):
        row_batches.append(list(range(ri, min(ri + max_rows, len(rows)))))
    
    for batch_idx, rb in enumerate(row_batches):
        sub_rows = [rows[r] for r in rb]
        
        # 多栏渲染：将所有panel渲染到同一张图片上
        panel_images = []
        for pi in range(n_panels):
            start_c = pi * cols_per_panel
            end_c = min(start_c + cols_per_panel, n_cols)
            if start_c >= n_cols:
                break
            sub_h = headers[start_c:end_c]
            sub_r = [[row[c] if c < len(row) else "" for c in range(start_c, end_c)] for row in sub_rows]
            
            panel_img = render_table(sub_h, sub_r, config, 
                                      title=f"[{pi+1}/{n_panels}]" if n_panels > 1 else None)
            panel_images.append(panel_img)
        
        if not panel_images:
            continue
        
        if len(panel_images) == 1:
            img = panel_images[0]
        else:
            # 横向拼接
            max_h = max(im.size[1] for im in panel_images)
            total_w = sum(im.size[0] for im in panel_images) + 5 * (len(panel_images) - 1)
            total_w = min(total_w, config.max_image_width)
            
            img = Image.new("RGB", (total_w, max_h), (255, 255, 255))
            x_offset = 0
            for pim in panel_images:
                img.paste(pim, (x_offset, 0))
                x_offset += pim.size[0] + 5
        
        n_parts = len(row_batches)
        fname = f"{base_name}_{batch_idx:03d}.png" if n_parts > 1 else f"{base_name}.png"
        images.append((fname, img))
    
    return images


def encode_file(filepath: str, output_dir: str = "output", 
                sheet: Optional[str] = None, 
                config: Optional[RenderConfig] = None) -> List[str]:
    """将数据文件编码为图片，返回图片路径列表"""
    if config is None:
        config = RenderConfig(density="dense")
    
    print(f"📖 读取: {filepath}")
    headers, rows = read_data(filepath, sheet)
    print(f"   {len(headers)} 列 × {len(rows)} 行")
    print(f"   密度: {config.density} ({config.font_size}pt/{config.dpi}dpi)")
    
    base_name = Path(filepath).stem
    images = smart_split_table(headers, rows, config, base_name)
    
    os.makedirs(output_dir, exist_ok=True)
    saved = []
    for fname, img in images:
        path = os.path.join(output_dir, fname)
        # PNG无损保存
        img.save(path, format="PNG", compress_level=1)  # 低压缩→读取快
        saved.append(path)
        print(f"  ✅ 已生成: {path} ({img.size[0]}×{img.size[1]}px)")
    
    print(f"\n📊 共 {len(saved)} 张图片，已保存至 {output_dir}/")
    
    # 生成元数据清单
    meta_path = os.path.join(output_dir, f"{base_name}_metadata.json")
    import json
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "source": filepath,
            "images": saved,
            "shape": [len(headers), len(rows)],
            "encoding": "table_render_v1",
        }, f, ensure_ascii=False, indent=2)
    print(f"  📋 元数据: {meta_path}")
    
    return saved


# ── CLI入口 ──────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="数据文档→图片高鲁棒编码器 v2.0（高密度版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              python data_encoder.py data.csv -o output/            # dense模式(默认)
              python data_encoder.py data.csv --density standard    # 标准模式(v1)
              python data_encoder.py data.csv --density ultra       # 极限密度(7pt/400dpi)
              python data_encoder.py data.xlsx -o output/ --sheet Sheet1
              python data_encoder.py data.csv --split 500
        """),
    )
    parser.add_argument("input", help="输入文件 (CSV/Excel/Numbers)")
    parser.add_argument("-o", "--output", default="output", help="输出目录 (默认: output/)")
    parser.add_argument("--sheet", default=None, help="Excel工作表名")
    parser.add_argument("--split", type=int, default=0, 
                        help="每张图片最大行数 (0=自动)")
    parser.add_argument("--density", choices=["standard", "dense", "ultra"], default="dense",
                        help="渲染密度: standard(14pt/低密度) dense(9pt/高密度) ultra(7pt/极限)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"❌ 文件不存在: {args.input}")
        return 1
    
    if not HAS_PIL:
        print("❌ 需要安装 Pillow: pip install Pillow")
        return 1
    
    try:
        config = RenderConfig(density=args.density)
        if args.split > 0:
            config.max_rows_per_image = args.split
        
        encode_file(args.input, args.output, args.sheet, config)
        return 0
    except Exception as e:
        print(f"❌ 编码失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    main()
