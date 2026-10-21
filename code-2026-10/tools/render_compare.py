#!/usr/bin/env python3
"""Render CSV vs TXTZ comparison image"""
from PIL import Image, ImageDraw, ImageFont
import os, csv

font_path = None
for candidate in ['DejaVuSansMono.ttf',
                  'C:/Windows/Fonts/consola.ttf',
                  'C:/Windows/Fonts/cour.ttf']:
    if os.path.exists(candidate):
        font_path = candidate
        break

if not font_path:
    for root, dirs, files in os.walk('C:/Windows/Fonts'):
        for f in files:
            if 'consol' in f.lower() or 'cour' in f.lower():
                font_path = os.path.join(root, f)
                break
        if font_path:
            break

if not font_path:
    font_path = 'C:/Windows/Fonts/consola.ttf'

print(f'Font: {font_path}')

font_size = 9
try:
    font = ImageFont.truetype(font_path, font_size)
except:
    font = ImageFont.load_default()

# Read CSV data (first 30 rows)
with open('test_data_5000.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.reader(f)
    all_rows = list(reader)
    csv_headers = all_rows[0]
    csv_rows = all_rows[1:31]

# Read TXTZ data
with open('test_5000_compact.txtz', 'r') as f:
    lines = f.read().strip().split('\n')
data_start = None
for i, line in enumerate(lines):
    if line.strip() == '---DATA---':
        data_start = i + 2
        break
txtz_lines = lines[data_start:data_start+30]

# Format texts
csv_text_lines = []
csv_text_lines.append(' '.join(csv_headers))
for row in csv_rows:
    csv_text_lines.append(' '.join(row))
csv_text = '\n'.join(csv_text_lines)

txty_header = '\n'.join(lines[:data_start-1])
txtz_text = txty_header + '\n' + '\n'.join(txtz_lines)

# Measure
def measure(text, f):
    max_w = 0
    for line in text.split('\n'):
        bbox = f.getbbox(line)
        w = bbox[2] - bbox[0] if bbox else 0
        max_w = max(max_w, w)
    return max_w

csv_w = int(measure(csv_text, font))
txtz_data = '\n'.join(txtz_lines)
txtz_data_w = int(measure(txtz_data, font))
txtz_full_w = int(measure(txtz_text, font))

line_h = 14
total_csv_lines = len(csv_text_lines)
total_txtz_lines = len(txtz_lines) + 3

img_w = csv_w + txtz_full_w + 60
img_h = max(total_csv_lines, total_txtz_lines) * line_h + 100

img = Image.new('RGB', (int(img_w), int(img_h)), 'white')
draw = ImageDraw.Draw(img)

title_font_size = 12
try:
    title_font = ImageFont.truetype(font_path, title_font_size)
except:
    title_font = ImageFont.load_default()

draw.text((10, 5), 'CSV (原始)', fill='#333', font=title_font)
draw.text((csv_w + 30, 5), 'TXTZ (紧凑格式)', fill='#333', font=title_font)

y = 30
for line in csv_text_lines:
    draw.text((10, y), line, fill='black', font=font)
    y += line_h

y = 30
for line in txtz_text.split('\n'):
    draw.text((csv_w + 30, y), line, fill='black', font=font)
    y += line_h

y_bottom = max(total_csv_lines, total_txtz_lines) * line_h + 40
draw.text((10, y_bottom + 5),
    f'CSV: {len(csv_text_lines)} 行, 最宽 {csv_w}px',
    fill='#666', font=title_font)
draw.text((10, y_bottom + 22),
    f'TXTZ: 数据区最宽 {txtz_data_w}px, 列宽缩减 {(1-txtz_data_w/csv_w)*100:.0f}%',
    fill='#c00', font=title_font)
draw.text((10, y_bottom + 39),
    f'TXTZ 完整: 数据行 + 12行元数据',
    fill='#666', font=title_font)

img.save('format_comparison.png')
print(f'✅ format_comparison.png')
print(f'  CSV宽度: {csv_w}px')
print(f'  TXTZ数据区: {txtz_data_w}px')
print(f'  宽度缩减: {(1-txtz_data_w/csv_w)*100:.0f}%')
