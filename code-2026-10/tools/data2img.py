#!/usr/bin/env python3
"""
data2img — 数据文档→高鲁棒性图片编码器 (单文件版)
====================================================
将 CSV/Excel 数据渲染为 OCR 可精确还原的 PNG 图片。
单文件，零外部依赖，跨平台 (Windows/Mac/Linux)，
发出即可用。

用法:
  python data2img.py data.csv                       # 默认输出到 output/
  python data2img.py data.xlsx -o images/           # 指定输出目录
  python data2img.py data.csv --density high        # 高密度模式
  python data2img.py data.csv --split 300           # 每张最多300行

首次运行如果缺包会提示安装:
  pip install Pillow openpyxl
"""

import csv
import json
import math
import os
import sys
import textwrap
from pathlib import Path
from typing import List, Optional, Tuple

# ═══════════════════════════════════════════════════════════
#  依赖检测 — 首次运行友好提示
# ═══════════════════════════════════════════════════════════

MISSING_PACKAGES = []

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    MISSING_PACKAGES.append("Pillow")

try:
    import openpyxl
except ImportError:
    pass  # 只有读 Excel 才需要，CSV 不需要

if MISSING_PACKAGES:
    print("=" * 60)
    print("  ❌ 缺少依赖包")
    print("=" * 60)
    print()
    print(f"  请先安装: pip install {' '.join(MISSING_PACKAGES)}")
    print()
    print("  示例:")
    print(f"    pip install {' '.join(MISSING_PACKAGES)}")
    print()
    print("  (如果 pip 报错，试试 pip3)")
    print("=" * 60)
    sys.exit(1)


# ═══════════════════════════════════════════════════════════
#  配置
# ═══════════════════════════════════════════════════════════

class Config:
    """渲染配置 — 平衡密度与 OCR 精度"""
    def __init__(self, density: str = "balanced"):
        self.font_path = self._find_best_font()
        
        if density == "balanced":
            self.font_size = 10
            self.header_size = 12
            self.pad_x = 3
            self.pad_y = 2
            self.border = 1
            self.dpi = 200
        elif density == "high":
            self.font_size = 8
            self.header_size = 10
            self.pad_x = 2
            self.pad_y = 1
            self.border = 1
            self.dpi = 200
        elif density == "safe":
            self.font_size = 12
            self.header_size = 14
            self.pad_x = 4
            self.pad_y = 3
            self.border = 1
            self.dpi = 200
        else:
            raise ValueError(f"未知密度: {density}")
        
        self.max_width = 4000
        self.max_height = 10000
        self.max_rows = 0  # 0=自动
        
        # 颜色
        self.bg = (255, 255, 255)
        self.fg = (0, 0, 0)
        self.header_bg = (230, 235, 245)
        self.line_color = (200, 205, 215)
    
    @staticmethod
    def _find_best_font() -> str:
        """跨平台找最佳等宽字体路径"""
        candidates = [
            "DejaVuSansMono.ttf",
            "DejaVu Sans Mono",
            "Consolas",
            "LiberationMono",
            "Courier New",
            "Courier",
        ]
        # 系统字体目录
        if sys.platform == "win32":
            dirs = ["C:/Windows/Fonts", os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts")]
        elif sys.platform == "darwin":
            dirs = ["/Library/Fonts", "/System/Library/Fonts", os.path.expanduser("~/Library/Fonts")]
        else:
            dirs = ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts")]
        
        for d in dirs:
            for name in candidates:
                p = os.path.join(d, name)
                if os.path.exists(p):
                    return p
        return ""


# ═══════════════════════════════════════════════════════════
#  数据读取
# ═══════════════════════════════════════════════════════════

def read_csv(filepath: str) -> Tuple[List[str], List[List[str]]]:
    """读取 CSV 文件"""
    rows = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(row)
    if not rows:
        return [], []
    return rows[0], rows[1:]


def read_excel(filepath: str, sheet: Optional[str] = None) -> Tuple[List[str], List[List[str]]]:
    """读取 Excel 文件"""
    if "openpyxl" not in sys.modules and "openpyxl" not in dir():
        print("读取 Excel 需要安装 openpyxl: pip install openpyxl")
        sys.exit(1)
    
    wb = openpyxl.load_workbook(filepath, read_only=True)
    ws = wb[sheet] if sheet else wb.active
    data = []
    for row in ws.iter_rows(values_only=True):
        data.append([str(c) if c is not None else "" for c in row])
    if not data:
        return [], []
    return data[0], data[1:]


def read_data(filepath: str) -> Tuple[List[str], List[List[str]], str]:
    """通用读取：自动识别格式"""
    ext = Path(filepath).suffix.lower()
    if ext == ".csv":
        return *read_csv(filepath), "CSV"
    elif ext in (".xlsx", ".xls"):
        return *read_excel(filepath), "Excel"
    elif ext in (".tsv", ".txt"):
        return *read_tsv(filepath), "TXT"
    else:
        print(f"不支持的文件格式: {ext} (仅支持 CSV / Excel)")
        sys.exit(1)


def read_tsv(filepath: str) -> Tuple[List[str], List[List[str]]]:
    """读取 Tab 分隔文件"""
    rows = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                rows.append(line.split("\t"))
    if not rows:
        return [], []
    return rows[0], rows[1:]


# ═══════════════════════════════════════════════════════════
#  智能格式化
# ═══════════════════════════════════════════════════════════

def _is_num(v: str) -> bool:
    if not v:
        return False
    c = v.replace(",", "").replace("-", "").replace(".", "").replace("%", "").replace("$", "")
    return bool(c) and c.isdigit()


def _fmt_val(v: str) -> str:
    """智能压缩数值显示"""
    if not v or v in ("nan", "None", "-"):
        return ""
    v = v.strip()
    try:
        f = float(v.replace(",", "").replace("%", "").replace("$", "").replace(" ", ""))
        if abs(f) >= 10000:
            return f"{f:.0f}"
        elif abs(f) >= 100:
            return f"{f:.1f}"
        elif "." in v:
            return f"{f:.2f}"
        return v
    except ValueError:
        pass
    return v if len(v) <= 16 else v[:13] + ".."


# ═══════════════════════════════════════════════════════════
#  渲染
# ═══════════════════════════════════════════════════════════

def render_table(headers: List[str], rows: List[List[str]],
                 cfg: Config, title: str = "") -> Image.Image:
    """将表格渲染为高对比度 PNG"""
    # 加载字体
    if cfg.font_path:
        font = ImageFont.truetype(cfg.font_path, cfg.font_size)
        hfont = ImageFont.truetype(cfg.font_path, cfg.header_size)
        tfont = ImageFont.truetype(cfg.font_path, cfg.header_size) if title else None
    else:
        font = ImageFont.load_default()
        hfont = ImageFont.load_default()
        tfont = ImageFont.load_default()
    
    # 格式化数据
    fmt_rows = []
    for row in rows:
        fmt_rows.append([_fmt_val(c) for c in row])
    rows = fmt_rows
    
    n_cols = len(headers)
    
    # 计算列宽
    col_widths = []
    for ci in range(n_cols):
        ml = len(str(headers[ci]))
        for r in rows:
            ml = max(ml, len(str(r[ci] if ci < len(r) else "")))
        cw = ml * cfg.font_size * 0.55 + cfg.pad_x * 2
        col_widths.append(max(int(cw), 40))
    
    rh = cfg.font_size * 1.4 + cfg.pad_y * 2
    hh = cfg.header_size * 1.4 + cfg.pad_y * 2
    title_h = cfg.header_size * 2 + 10 if title else 0
    
    total_w = int(sum(col_widths) + cfg.border * n_cols + 10)
    total_w = min(total_w, cfg.max_width)
    total_h = int(title_h + hh + len(rows) * rh + 10)
    total_h = min(total_h, cfg.max_height)
    
    img = Image.new("RGB", (total_w, total_h), cfg.bg)
    draw = ImageDraw.Draw(img)
    
    y = 5
    if title:
        draw.text((5, y), title, fill=cfg.fg, font=tfont)
        y += title_h
    
    # 表头
    draw.rectangle([5, y, total_w - 5, y + hh],
                   fill=cfg.header_bg, outline=cfg.fg, width=cfg.border)
    x = 5 + cfg.border
    for ci, h in enumerate(headers):
        tx = x + sum(col_widths[:ci]) + cfg.pad_x
        draw.text((tx, y + cfg.pad_y), str(h), fill=cfg.fg, font=hfont)
        if ci > 0:
            lx = x + sum(col_widths[:ci])
            draw.line([(lx, y + 2), (lx, y + hh - 2)], fill=cfg.line_color)
    y += hh
    
    # 数据行
    for ri, row in enumerate(rows):
        if ri > 0 and ri % 5 == 0:
            draw.line([(5, y), (total_w - 5, y)], fill=cfg.line_color)
        
        for ci in range(n_cols):
            val = str(row[ci]) if ci < len(row) else ""
            tx = x + sum(col_widths[:ci]) + cfg.pad_x
            if _is_num(val):
                tw = len(val) * cfg.font_size * 0.55
                tx = x + sum(col_widths[:ci]) + col_widths[ci] - cfg.pad_x - int(tw)
            draw.text((tx, y + cfg.pad_y), val, fill=cfg.fg, font=font)
        y += rh
    
    return img


# ═══════════════════════════════════════════════════════════
#  分割+编码
# ═══════════════════════════════════════════════════════════

def encode(headers: List[str], rows: List[List[str]],
           output_dir: str, cfg: Config,
           basename: str = "data") -> List[str]:
    """分页编码为多张图片"""
    os.makedirs(output_dir, exist_ok=True)
    
    # 自动计算每图行数
    rh = cfg.font_size * 1.4 + cfg.pad_y * 2
    hh = cfg.header_size * 1.4 + cfg.pad_y * 2
    max_rows = cfg.max_rows or max(1, int((cfg.max_height - hh - 20) / rh))
    
    n_cols = len(headers)
    
    # 多栏: >6列分2栏, >12分3栏
    panels = 1
    if n_cols > 12:
        panels = 3
    elif n_cols > 6:
        panels = 2
    cpp = (n_cols + panels - 1) // panels
    
    saved = []
    for bi in range(0, len(rows), max_rows):
        batch = rows[bi:bi + max_rows]
        
        panel_imgs = []
        for pi in range(panels):
            sc = pi * cpp
            ec = min(sc + cpp, n_cols)
            if sc >= n_cols:
                break
            sub_h = headers[sc:ec]
            sub_r = [[r[c] if c < len(r) else "" for c in range(sc, ec)] for r in batch]
            ti = f"[{pi + 1}/{panels}]" if panels > 1 else ""
            panel_imgs.append(render_table(sub_h, sub_r, cfg, ti))
        
        if not panel_imgs:
            continue
        
        if len(panel_imgs) == 1:
            img = panel_imgs[0]
        else:
            mh = max(im.height for im in panel_imgs)
            tw = min(sum(im.width for im in panel_imgs) + 5 * (len(panel_imgs) - 1), cfg.max_width)
            img = Image.new("RGB", (tw, mh), (255, 255, 255))
            ox = 0
            for pim in panel_imgs:
                img.paste(pim, (ox, 0))
                ox += pim.width + 5
        
        fname = f"{basename}_{bi // max_rows:03d}.png"
        fpath = os.path.join(output_dir, fname)
        img.save(fpath, format="PNG", compress_level=1)
        saved.append(fpath)
        print(f"  ✅ {fname}  ({img.width}×{img.height}px, {os.path.getsize(fpath) // 1024}KB)")
    
    return saved


# ═══════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="data2img — 数据文档→图片编码器 (单文件版)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              python data2img.py data.csv
              python data2img.py data.xlsx -o images/
              python data2img.py data.csv --density high
              python data2img.py data.csv --split 300
        """),
    )
    parser.add_argument("input", help="输入文件 (CSV / Excel)")
    parser.add_argument("-o", "--output", default="output", help="输出目录 (默认: output/)")
    parser.add_argument("--density", choices=["safe", "balanced", "high"],
                        default="balanced", help="渲染密度 (默认: balanced)")
    parser.add_argument("--split", type=int, default=0,
                        help="每张图片最大行数 (0=自动)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"❌ 文件不存在: {args.input}")
        return 1
    
    print("=" * 50)
    print("📦 data2img — 数据→图片编码器")
    print("=" * 50)
    print()
    
    # 读取
    headers, rows, fmt = read_data(args.input)
    print(f"📖 {fmt}: {args.input}")
    print(f"   {len(headers)} 列 × {len(rows)} 行")
    
    # 配置
    cfg = Config(args.density)
    if args.split:
        cfg.max_rows = args.split
    print(f"  密度: {args.density} ({cfg.font_size}pt)")
    
    # 编码
    print(f"\n🖼️  编码中...")
    basename = Path(args.input).stem
    images = encode(headers, rows, args.output, cfg, basename)
    
    # 统计
    total_kb = sum(os.path.getsize(f) for f in images) / 1024
    total_cells = len(headers) * len(rows)
    
    print(f"\n{'=' * 50}")
    print(f"✅ 完成! {len(images)} 张图片 → {args.output}/")
    print(f"   数据: {total_cells:,} 单元格")
    print(f"   大小: {total_kb:.0f}KB  ({total_kb / max(len(images), 1):.0f}KB/张)")
    print(f"{'=' * 50}")
    
    return 0


if __name__ == "__main__":
    main()
