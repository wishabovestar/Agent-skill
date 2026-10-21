#!/usr/bin/env python3
"""用 qwen2.5vl:3b 分块识别图纸FAI表 - 逐区域精确提取"""
import base64, json, urllib.request, io, sys, time
from PIL import Image

def ask_vlm(img, prompt, timeout=300):
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    img_b64 = base64.b64encode(buf.getvalue()).decode()
    payload = {
        'model': 'qwen2.5vl:3b',
        'messages': [{'role': 'user', 'content': prompt, 'images': [img_b64]}],
        'stream': False,
        'options': {'temperature': 0.1}
    }
    req = urllib.request.Request('http://localhost:11434/api/chat',
        data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read().decode()).get('message', {}).get('content', '')

img = Image.open(r'D:\hermes\analysis\.pdf_cache\new_pages\page6.png')
w, h = img.size
print(f'原始: {w}x{h}')

# 先整体看布局 (缩小到 1400 宽)
small = img.copy()
small.thumbnail((1400, 1400))
print('\n=== 整体布局 ===')
try:
    r = ask_vlm(small, '描述这个页面的布局: 表格在什么位置? 有多少行? 列标题是什么? 用中文回答')
    print(r[:800])
except Exception as e:
    print(f'ERR: {e}')

# 表格区域: 裁剪下半部 3 个横向条带, 每个放大到合适尺寸
bands = [
    (0.30, 0.45, '表格上部(FAI 1-10)'),
    (0.45, 0.60, '表格中部(FAI 11-22)'),
    (0.60, 0.75, '表格下部(FAI 23-36)'),
]
for y0, y1, label in bands:
    print(f'\n===== {label} =====')
    crop = img.crop((0, int(h*y0), w, int(h*y1)))
    # 放大到可读 (保持比例)
    crop = crop.resize((int(crop.width * 1.5), int(crop.height * 1.5)), Image.LANCZOS)
    print(f'区域: {crop.size}')
    try:
        r = ask_vlm(crop, '这是工程图纸的FAI测量表区域。逐行识别表格内容, 输出格式: 编号|特征名|名义值|上公差|下公差|测量方法。看不清的写[?]')
        print(r[:1500])
    except Exception as e:
        print(f'ERR: {e}')
    time.sleep(2)
