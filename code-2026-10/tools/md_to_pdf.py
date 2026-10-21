#!/usr/bin/env python3
"""SPSS教程 Markdown → PDF 转换 (中文支持)"""
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, Preformatted, PageBreak)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT

# ===== 中文字体注册 =====
pdfmetrics.registerFont(TTFont('MSYH', r'C:\Windows\Fonts\msyh.ttc'))
pdfmetrics.registerFont(TTFont('MSYH-B', r'C:\Windows\Fonts\msyhbd.ttc'))

# ===== 样式 =====
title_style = ParagraphStyle('Title', fontName='MSYH-B', fontSize=20, leading=28,
    textColor=HexColor('#1a1a2e'), spaceAfter=12, alignment=1)
h1_style = ParagraphStyle('H1', fontName='MSYH-B', fontSize=16, leading=22,
    textColor=HexColor('#16213e'), spaceBefore=16, spaceAfter=8)
h2_style = ParagraphStyle('H2', fontName='MSYH-B', fontSize=13, leading=18,
    textColor=HexColor('#0f3460'), spaceBefore=12, spaceAfter=6)
body_style = ParagraphStyle('Body', fontName='MSYH', fontSize=10, leading=16,
    textColor=HexColor('#333333'), spaceAfter=4)
code_style = ParagraphStyle('Code', fontName='MSYH', fontSize=8.5, leading=13,
    textColor=HexColor('#004d40'), backColor=HexColor('#f5f5f5'),
    borderPadding=6, spaceAfter=8, leftIndent=10)
table_style = TableStyle([
    ('BACKGROUND', (0,0), (-1,0), HexColor('#0f3460')),
    ('TEXTCOLOR', (0,0), (-1,0), HexColor('#ffffff')),
    ('FONTNAME', (0,0), (-1,-1), 'MSYH'),
    ('FONTSIZE', (0,0), (-1,-1), 9),
    ('GRID', (0,0), (-1,-1), 0.5, HexColor('#cccccc')),
    ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#ffffff'), HexColor('#f0f4f8')]),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ('TOPPADDING', (0,0), (-1,-1), 4),
    ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ('LEFTPADDING', (0,0), (-1,-1), 6),
    ('RIGHTPADDING', (0,0), (-1,-1), 6),
])

def escape(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def parse_md(md_text):
    """解析markdown为reportlab元素"""
    elements = []
    lines = md_text.split('\n')
    i = 0
    in_code = False
    code_buf = []
    table_buf = []

    def flush_table():
        if not table_buf:
            return
        rows = []
        for row in table_buf:
            cells = [c.strip() for c in row.strip('|').split('|')]
            rows.append(cells)
        # 分离表头和数据
        data = rows
        if len(data) > 1:
            t = Table(data, colWidths=None)
            t.setStyle(table_style)
            elements.append(t)
            elements.append(Spacer(1, 8))
        table_buf.clear()

    while i < len(lines):
        line = lines[i]
        # 代码块
        if line.strip().startswith('```'):
            if in_code:
                elements.append(Preformatted('\n'.join(code_buf), code_style))
                code_buf = []
                in_code = False
            else:
                flush_table()
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue

        # 表格行
        if line.strip().startswith('|') and '|' in line[1:]:
            # 跳过分隔行 |---|
            if re.match(r'^\|[\s\-:|]+\|$', line.strip()):
                i += 1
                continue
            table_buf.append(line)
            i += 1
            continue
        else:
            flush_table()

        s = line.strip()
        # 标题
        if s.startswith('# ') or s.startswith('## ') or s.startswith('### '):
            level = len(s) - len(s.lstrip('#'))
            text = escape(s.lstrip('#').strip())
            if level == 1:
                elements.append(Paragraph(text, h1_style))
            elif level == 2:
                elements.append(Paragraph(text, h2_style))
            else:
                elements.append(Paragraph(text, ParagraphStyle('H3', parent=h2_style, fontSize=11)))
        elif s.startswith('- ') or s.startswith('* '):
            elements.append(Paragraph('• ' + escape(s[2:]), body_style))
        elif s.startswith('**') and s.endswith('**'):
            elements.append(Paragraph(escape(s.strip('*')), ParagraphStyle('B', parent=h2_style, fontSize=12)))
        elif s == '---':
            elements.append(Spacer(1, 6))
        elif s:
            # 行内格式处理
            text = escape(s)
            text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
            text = re.sub(r'`(.+?)`', r'<font color="#00695c">\1</font>', text)
            elements.append(Paragraph(text, body_style))
        i += 1

    flush_table()
    if code_buf:
        elements.append(Preformatted('\n'.join(code_buf), code_style))
    return elements

def main():
    md_path = r'D:/hermes/data/spss_tutorial_beginner.md'
    pdf_path = r'D:/hermes/data/SPSS新手入门教程.pdf'
    title = 'SPSS 新手入门教程'
    subtitle = '从零开始，5分钟上手数据分析'

    with open(md_path, encoding='utf-8') as f:
        md = f.read()

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=18*mm, bottomMargin=18*mm,
        title=title,
        author='Hermes'
    )

    elements = []
    elements.append(Paragraph(title, title_style))
    elements.append(Paragraph(subtitle,
        ParagraphStyle('Sub', parent=body_style, fontSize=11, textColor=HexColor('#666666'), alignment=1)))
    elements.append(Spacer(1, 10))
    elements.extend(parse_md(md))

    doc.build(elements)
    print(f'✅ PDF生成完成: {pdf_path}')

if __name__ == '__main__':
    main()
