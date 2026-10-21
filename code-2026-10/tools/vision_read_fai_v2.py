#!/usr/bin/env python3
"""v2: 用 qwen2.5vl:3b 精细分块识别FAI表 - 缩小到模型可处理尺寸"""
import base64, json, urllib.request, io, time
from PIL import Image

def ask_vlm(img, prompt, timeout=240):
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

# FAI表通常在页面下部 30%-80% 区域, 切成6个竖向条带
# 每个条带宽度=全宽, 高度=8%, 缩放到 1800px 宽
strip_h = 0.08
for i in range(6):
    y0 = int(h * (0.30 + i * strip_h))
    y1 = int(h * (0.30 + (i+1) * strip_h))
    crop = img.crop((0, y0, w, y1))
    # 缩放到1800宽
    scale = 1800 / crop.width
    crop = crop.resize((1800, int(crop.height * scale)), Image.LANCZOS)
    print(f'\n===== 条带{i+1} (y {y0}-{y1}, {crop.size}) =====')
    try:
        r = ask_vlm(crop, '这是工程图纸FAI测量表。识别表格行的全部内容。输出格式(每行一条): Sheet|编号|特征描述|名义值|上公差|下公差|测量方法。看不清的用[?]')
        print(r[:1200])
    except Exception as e:
        print(f'ERR: {type(e).__name__} {str(e)[:100]}')
    time.sleep(1)
