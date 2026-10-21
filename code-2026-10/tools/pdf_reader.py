"""
PDF图纸阅读器 v1.0 — 工程图纸/技术文档/扫描件
===============================================
功能:
  1. 提取文本内容 (含表格/段落)
  2. 提取图片/工程图
  3. 提取元数据 (作者/页数/尺寸)
  4. 图纸尺寸标注识别 (针对工程图纸)
  5. OCR回退 (扫描件PDF)
  6. 多页预览/摘要

依赖: pypdf (纯Python, 已安装)
"""

import json, re, os, hashlib, time
from pathlib import Path
from typing import Optional
from collections import Counter

try:
    from pypdf import PdfReader, PdfWriter
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

# ── 配置 ──
PDF_CACHE_DIR = Path("D:/hermes/analysis/.pdf_cache")
PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════
# 1. 核心PDF读取器
# ═══════════════════════════════════════════════════

class PDFReader:
    """
    PDF文件阅读器 — 支持工程图纸/技术文档
    可提取: 文本/元数据/图片/表格/尺寸标注
    """

    def __init__(self, filepath: str):
        self.path = Path(filepath)
        self.name = self.path.name
        self.size = self.path.stat().st_size if self.path.exists() else 0
        self.reader = None
        self.metadata = {}
        self.total_pages = 0

    def open(self) -> bool:
        """打开PDF文件"""
        if not self.path.exists():
            return False
        if not HAS_PYPDF:
            return False
        try:
            self.reader = PdfReader(str(self.path))
            self.total_pages = len(self.reader.pages)
            self.metadata = {
                "file": self.name,
                "size_bytes": self.size,
                "size_kb": round(self.size / 1024, 1),
                "pages": self.total_pages,
                "pdf_version": self.reader.pdf_header if hasattr(self.reader, 'pdf_header') else "",
            }
            # 元数据
            if self.reader.metadata:
                meta = {}
                for k, v in self.reader.metadata.items():
                    k_clean = k.replace("/", "").lower()
                    if v: meta[k_clean] = str(v)[:100]
                self.metadata["metadata"] = meta
            return True
        except Exception as e:
            self.error = str(e)
            return False

    def extract_text(self, page_num: int = None, max_pages: int = 5) -> str:
        """
        提取文本: 单页或前N页
        """
        if not self.reader:
            return ""

        pages_to_read = []
        if page_num is not None:
            pages_to_read = [page_num]
        else:
            pages_to_read = range(min(max_pages, self.total_pages))

        text = ""
        for i in pages_to_read:
            try:
                page = self.reader.pages[i]
                page_text = page.extract_text()
                if page_text.strip():
                    text += f"\n--- 第{i+1}页 ---\n{page_text}"
            except:
                pass

        return text

    def extract_all_text(self) -> dict:
        """
        提取全部页面的文本，按页分组
        返回: {page_num: text}
        """
        if not self.reader:
            return {}

        result = {}
        for i in range(self.total_pages):
            try:
                page = self.reader.pages[i]
                text = page.extract_text()
                if text.strip():
                    result[i + 1] = text.strip()
            except:
                result[i + 1] = "[提取失败]"
        return result

    def extract_images_meta(self) -> list[dict]:
        """
        提取PDF中嵌入的图片元信息 (无PIL也能获取尺寸/数量)
        返回: [{page, index, width, height, size}]
        """
        images = []
        if not self.reader:
            return images

        for page_num in range(min(self.total_pages, 20)):
            try:
                page = self.reader.pages[page_num]
                if '/XObject' in page['/Resources']:
                    xobjects = page['/Resources']['/XObject']
                    img_count = 0
                    for obj_name in xobjects:
                        obj = xobjects[obj_name]
                        if obj['/Subtype'] == '/Image':
                            w = obj.get('/Width', 0)
                            h = obj.get('/Height', 0)
                            img_count += 1
                            images.append({
                                "page": page_num + 1,
                                "index": img_count,
                                "width": w,
                                "height": h,
                                "type": str(obj.get('/Filter', 'raw')),
                            })
            except:
                pass
        return images

    def extract_dimensions(self) -> list[dict]:
        """
        尝试识别工程图纸中的尺寸标注
        基于文本模式匹配: 数字+单位
        """
        dims = []
        if not self.reader:
            return dims

        # 尺寸标注模式
        dim_patterns = [
            (r'\b(\d+\.?\d*)\s*mm\b', 'mm'),
            (r'\b(\d+\.?\d*)\s*cm\b', 'cm'),
            (r'\b(\d+\.?\d*)\s*m\b', 'm'),
            (r'\b(\d+\.?\d*)\s*inch(?:es)?\b', 'inch'),
            (r'\b(\d+\.?\d*)\s*°\b', '度'),
            (r'±(\d+\.?\d*)', '公差'),
            (r'R(\d+\.?\d*)', '半径'),
            (r'Ø(\d+\.?\d*)', '直径'),
            (r'M(\d+)', '螺纹'),
        ]

        for page_num in range(min(self.total_pages, 10)):
            try:
                text = self.reader.pages[page_num].extract_text()
                for pattern, unit in dim_patterns:
                    matches = re.findall(pattern, text)
                    for m in matches:
                        dims.append({
                            "page": page_num + 1,
                            "value": m if isinstance(m, str) else m[0],
                            "unit": unit,
                        })
            except:
                pass

        return dims

    def summary(self) -> dict:
        """
        生成PDF摘要:
          - 元数据
          - 文本量估算
          - 图片数量
          - 尺寸标注 (工程图)
          - 检测是否为工程图纸
        """
        result = {**self.metadata}

        if not self.reader:
            result["error"] = "文件未打开"
            return result

        # 文本量
        text = self.extract_text(max_pages=3)
        result["text_chars"] = len(text)
        result["text_preview"] = text[:300]

        # 图片
        images = self.extract_images_meta()
        result["images"] = len(images)
        result["image_details"] = images[:5]

        # 尺寸标注 (工程图纸检测)
        dims = self.extract_dimensions()
        result["dimensions_found"] = len(dims)
        result["dimension_preview"] = dims[:10]

        # 检测是否为工程图纸
        is_engineering = False
        if dims or result.get("images", 0) > 5:
            is_engineering = True
        if any(kw in text.lower() for kw in ["drawing", "图纸", "tolerance", "公差",
                                                "scale", "比例", "material", "材料"]):
            is_engineering = True
        result["is_engineering_drawing"] = is_engineering

        # 图纸尺寸 (页面物理尺寸)
        try:
            page = self.reader.pages[0]
            box = page.mediabox
            w_pt = box.width if hasattr(box, 'width') else 0
            h_pt = box.height if hasattr(box, 'height') else 0
            result["page_width_mm"] = round(float(w_pt) * 0.3528, 1)
            result["page_height_mm"] = round(float(h_pt) * 0.3528, 1)
            # 检测图纸幅面
            w_mm = result["page_width_mm"]
            h_mm = result["page_height_mm"]
            if abs(w_mm - 841) < 10 and abs(h_mm - 1189) < 10:
                result["format"] = "A0"
            elif abs(w_mm - 594) < 10 and abs(h_mm - 841) < 10:
                result["format"] = "A1"
            elif abs(w_mm - 420) < 10 and abs(h_mm - 594) < 10:
                result["format"] = "A2"
            elif abs(w_mm - 297) < 10 and abs(h_mm - 420) < 10:
                result["format"] = "A3"
            elif abs(w_mm - 210) < 10 and abs(h_mm - 297) < 10:
                result["format"] = "A4"
            else:
                result["format"] = f"{w_mm:.0f}x{h_mm:.0f}mm(非标)"
        except:
            pass

        return result


# ═══════════════════════════════════════════════════
# 2. 工程图纸专用提取
# ═══════════════════════════════════════════════════

class EngineeringDrawingExtractor:
    """工程图纸专用: 尺寸/标题栏/材料/BOM表"""

    def __init__(self, pdf_reader: PDFReader):
        self.reader = pdf_reader

    def extract_title_block(self) -> dict:
        """
        提取图纸标题栏信息:
          图号/名称/材料/比例/设计者/日期
        """
        text = self.reader.extract_text(max_pages=1)
        result = {}

        patterns = {
            "drawing_number": [r'(?:图号|图纸编号|DWG\s*NO[.:]?)\s*[:：]?\s*([\w\-./]+)',
                               r'(?:Part\s*No|Part\s*Number)[.:]?\s*([\w\-./]+)'],
            "title": [r'(?:名称|品名|零件名|Description)[:：]?\s*(.+)'],
            "material": [r'(?:材料|Material)[:：]?\s*(.+)'],
            "scale": [r'(?:比例|Scale)[:：]?\s*(\d+\s*[:：]\s*\d+)'],
            "designer": [r'(?:设计|Design|制图|Drawn)[:：]?\s*(.+)'],
            "date": [r'(?:日期|Date)[:：]?\s*([\d\-/.]+)'],
            "weight": [r'(?:重量|Weight)[:：]?\s*([\d.]+)\s*(?:g|kg)'],
            "revision": [r'(?:版本|Rev(?:ision)?)[.:]?\s*([\w.]+)'],
            "company": [r'(博众精工|Bozhon|华为|Foxconn|Apple)'],
        }

        for key, pat_list in patterns.items():
            for pat in pat_list:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    result[key] = m.group(1).strip()
                    break

        return result

    def extract_bom(self) -> list[dict]:
        """
        提取图纸BOM表 (物料清单)
        基于表格结构识别
        """
        text = self.reader.extract_text(max_pages=2)
        items = []

        # 常见的BOM表头
        bom_headers = ["序号", "物料编号", "名称", "数量", "材料", "备注",
                       "NO", "PART NUMBER", "DESCRIPTION", "QTY", "MATERIAL"]

        lines = text.split('\n')
        in_bom = False
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 检测BOM表头
            if any(h in line.upper() for h in bom_headers) and len(line) < 100:
                in_bom = True
                continue
            if in_bom:
                # 尝试解析行: 序号/编号/名称/数量
                parts = re.split(r'\s{2,}|\t', line)
                if len(parts) >= 2:
                    items.append({
                        "raw": line[:80],
                        "parts": parts,
                    })

        return items[:20]


# ═══════════════════════════════════════════════════
# 3. 批量处理
# ═══════════════════════════════════════════════════

class PDFBatchProcessor:
    """批量PDF处理"""

    @staticmethod
    def scan_directory(directory: str, recursive: bool = True) -> list[dict]:
        """扫描目录下所有PDF文件"""
        pdfs = []
        path = Path(directory)
        pattern = "**/*.pdf" if recursive else "*.pdf"
        for f in sorted(path.glob(pattern)):
            pdfs.append({
                "path": str(f),
                "name": f.name,
                "size_kb": round(f.stat().st_size / 1024, 1),
            })
        return pdfs

    @staticmethod
    def batch_summarize(directory: str, max_files: int = 20) -> list[dict]:
        """批量生成PDF摘要"""
        files = PDFBatchProcessor.scan_directory(directory)[:max_files]
        results = []
        for f in files:
            reader = PDFReader(f["path"])
            if reader.open():
                results.append(reader.summary())
        return results


# ── 图纸分析选项生成器 ──

def _generate_analysis_options(dims: dict, title_block: dict = None) -> list[dict]:
    """
    基于图纸内容自动生成可行的分析选项。
    根据尺寸类型和标题栏信息动态调整。
    """
    options = []

    has_tolerance = '公差' in dims
    has_diameter = '直径' in dims or '半径' in dims
    has_thread = '螺纹' in dims
    has_3d_size = '长×宽' in dims
    has_thickness = '厚度' in dims or '深度' in dims
    has_angle = '度' in dims or '角度' in dims
    is_mechanical = any(k in str(title_block or {}) for k in ['材料', 'Material', '比例', 'Scale'])

    if has_tolerance:
        options.append({
            "title": "公差分析 (Tolerance Analysis)",
            "desc": "对尺寸公差链进行分析，评估装配可行性",
            "agents": ["构形(gouxing)", "算渊(applied_math)"],
        })
    if is_mechanical or has_3d_size:
        options.append({
            "title": "可制造性分析 (DFM Analysis)",
            "desc": "检查壁厚/拔模角/倒扣/尖角等制造约束",
            "agents": ["构形(gouxing)", "明鉴(analyst)"],
        })
    if has_diameter or has_3d_size or has_thickness:
        options.append({
            "title": "3D模型重建",
            "desc": "基于图纸尺寸重建三维模型",
            "agents": ["构形(gouxing)", "绘影(designer)"],
        })
    if is_mechanical and (has_3d_size or has_thickness):
        options.append({
            "title": "结构强度估算",
            "desc": "基于尺寸和材料估算结构强度/刚度",
            "agents": ["算渊(applied_math)", "程实(process_engineer)"],
        })
    options.append({
        "title": "BOM物料清单提取",
        "desc": "提取图纸中的物料清单/零件明细表",
        "agents": ["琢言(writer)", "通量(data_scientist)"],
    })
    options.append({
        "title": "尺寸汇总报告",
        "desc": "将图纸所有尺寸生成结构化报告 (Markdown/Excel)",
        "agents": ["琢言(writer)", "通量(data_scientist)"],
    })
    if has_3d_size or has_diameter:
        options.append({
            "title": "装配干涉检查",
            "desc": "检查多零件装配中是否存在干涉",
            "agents": ["构形(gouxing)", "明鉴(analyst)"],
        })
    if is_mechanical:
        options.append({
            "title": "制造工艺规划",
            "desc": "基于图纸制定加工工艺流程",
            "agents": ["程实(process_engineer)", "构形(gouxing)"],
        })
    return options


def run_dim_command(path: str) -> dict:
    """供其他模块调用的尺寸分析接口"""
    reader = PDFReader(path)
    if not reader.open():
        return {"error": "打开失败"}
    dims = reader.organize_dimensions()
    tb = EngineeringDrawingExtractor(reader).extract_title_block()
    return {
        "title_block": tb,
        "dimensions": dims,
        "suggestions": _generate_analysis_options(dims, tb),
    }


# ── CLI ──

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("📄 PDF图纸阅读器 v1.0")
        print()
        print("用法:")
        print("  read <file.pdf>           读取PDF文本")
        print("  info <file.pdf>           PDF详细信息")
        print("  dims <file.pdf>           提取尺寸标注")
        print("  bom <file.pdf>            提取BOM表")
        print("  batch <directory>          批量处理目录")
        print("  scan <directory>           扫描PDF文件")
        sys.exit(0)

    cmd = sys.argv[1]
    path = sys.argv[2] if len(sys.argv) > 2 else "."

    if cmd == "read":
        reader = PDFReader(path)
        if reader.open():
            text = reader.extract_text(max_pages=10)
            print(f"📄 {reader.name} ({reader.total_pages}页)")
            print(f"   文本: {len(text)} chars")
            print(text[:2000])
        else:
            print(f"❌ 打开失败: {getattr(reader, 'error', '未知')}")

    elif cmd == "info":
        reader = PDFReader(path)
        if reader.open():
            info = reader.summary()
            print(f"📄 {info.get('file', '?')}")
            print(f"   页数: {info.get('pages', 0)}")
            print(f"   大小: {info.get('size_kb', 0)} KB")
            print(f"   文本量: {info.get('text_chars', 0)} chars")
            print(f"   图片: {info.get('images', 0)} 张")
            print(f"   尺寸标注: {info.get('dimensions_found', 0)} 个")
            print(f"   工程图纸: {'✅' if info.get('is_engineering_drawing') else '❌'}")
            print(f"   页面幅面: {info.get('format', '?')}")
            if info.get('metadata'):
                print(f"   元数据: {json.dumps(info['metadata'], ensure_ascii=False)}")
            if info.get('images'):
                for img in info.get('image_details', [])[:3]:
                    print(f"   图片: 第{img['page']}页 {img['width']}x{img['height']}px {img['type']}")
        else:
            print(f"❌ 打开失败")

    elif cmd == "dims":
        """提取尺寸 → 归纳汇总 → 分析建议"""
        reader = PDFReader(path)
        if reader.open():
            eng = EngineeringDrawingExtractor(reader)
            tb = eng.extract_title_block()
            if tb:
                print("📋 标题栏:")
                for k, v in tb.items():
                    print(f"   {k}: {v}")
            dims = reader.organize_dimensions()
            total = sum(len(v) for v in dims.values())
            print(f"\n📐 尺寸归纳汇总 ({total}个):")
            for unit, values in dims.items():
                print(f"  {unit}: {', '.join(str(v) for v in values[:10])}{'...' if len(values)>10 else ''}")

            # 自动生成分析选项
            suggestions = _generate_analysis_options(dims, tb)
            print(f"\n{'='*55}")
            print("🔍 图纸分析建议")
            print(f"{'='*55}")
            for i, s in enumerate(suggestions, 1):
                print(f"\n  [{i}] {s['title']}")
                print(f"      {s['desc']}")
                if s.get('agents'):
                    print(f"      调用: {', '.join(s['agents'])}")
            print(f"\n  [其他] 自定义分析需求")
            print(f"\n💡 请输入分析编号或描述你的分析需求：")
        else:
            print(f"❌ 打开失败")

    elif cmd == "bom":
        reader = PDFReader(path)
        if reader.open():
            eng = EngineeringDrawingExtractor(reader)
            bom = eng.extract_bom()
            print(f"📋 BOM表 ({len(bom)}行):")
            for item in bom[:15]:
                print(f"   {item['raw']}")
        else:
            print(f"❌ 打开失败")

    elif cmd == "batch":
        results = PDFBatchProcessor.batch_summarize(path)
        print(f"📚 批量处理: {len(results)} 个PDF")
        for r in results:
            eng = "📐" if r.get("is_engineering_drawing") else "📄"
            print(f"  {eng} {r.get('file','?')[:40]:40} {r.get('pages',0)}页 "
                  f"{r.get('text_chars',0)}字 {r.get('images',0)}图 "
                  f"{r.get('format','?')}")

    elif cmd == "scan":
        files = PDFBatchProcessor.scan_directory(path)
        print(f"📚 PDF文件: {len(files)} 个")
        for f in files[:30]:
            print(f"  {f['name'][:50]:50} {f['size_kb']:>7} KB")
