#!/usr/bin/env python3
"""v3: 高条带重叠识别FAI表 - 每个条带12%高+50%重叠"""
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

# FAI表区域: 25%-85%, 每个条带14%高, 步进7% (50%重叠)
y_start = 0.25
y_end = 0.85
step = 0.07
band_h = 0.14
y = y_start
idx = 0
results = []
while y < y_end - 0.05:
    y0 = int(h * y)
    y1 = int(h * min(y + band_h, y_end))
    crop = img.crop((0, y0, w, y1))
    scale = 2000 / crop.width
    crop = crop.resize((2000, max(200, int(crop.height * scale))), Image.LANCZOS)
    idx += 1
    print(f'\n===== 带{idx} (y {y0}-{y1}, {crop.size}) =====', flush=True)
    try:
        r = ask_vlm(crop, '识别工程图纸FAI测量表行。输出每行: Sheet|编号|特征描述|名义值|上公差|下公差|方法。逐行精确,看不清用[?]')
        print(r[:1500], flush=True)
        results.append(f'## 带{idx} (y{y0}-{y1})\n{r}')
    except Exception as e:
        print(f'ERR: {type(e).__name__} {str(e)[:80]}', flush=True)
    y += step
    time.sleep(1)

# 保存全部结果
with open(r'D:\hermes\analysis\vision_fai_results_v3.txt', 'w', encoding='utf-8') as f:
    f.write('\n\n'.join(results))
print('\n=== 已保存 vision_fai_results_v3.txt ===', flush=True)
