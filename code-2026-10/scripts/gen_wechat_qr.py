#!/usr/bin/env python3
"""WeChat iLink Bot QR Code Generator - QR重新认证"""
import json, ssl, urllib.request, os, sys
from pathlib import Path

# 硬编码路径避免Path对象问题
HERMES_HOME = "D:\\hermes\\hermes-data\\profiles\\mybot"
ENV_FILE = os.path.join(HERMES_HOME, ".env")

# 读env
env = {}
with open(ENV_FILE, encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k] = v

TOKEN = env.get('WEIXIN_TOKEN', '')
BASE = env.get('WEIXIN_BASE_URL', 'https://ilinkai.weixin.qq.com')
print(f"Token前20: {TOKEN[:20]}... 长度: {len(TOKEN)}")

# SSL绕过
ctx = ssl._create_unverified_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

url = f'{BASE}/ilink/bot/get_bot_qrcode?bot_type=3'
req = urllib.request.Request(url, headers={'Authorization': f'Bearer {TOKEN}'})
try:
    resp = urllib.request.urlopen(req, context=ctx, timeout=30)
    body = resp.read()
    data = json.loads(body)
    print(f'API响应: {json.dumps(data, ensure_ascii=False)[:500]}')
    
    qr_url = data.get('qrcode_img_content', '') or data.get('qrcode', '')
    qr_val = data.get('qrcode', '')
    scan_data = qr_url if qr_url else qr_val
    
    if not scan_data:
        print("❌ 无QR数据返回")
        sys.exit(1)
    
    print(f'QR值: {scan_data[:100]}...')
    
    import qrcode
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(scan_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    img_path = os.path.join(HERMES_HOME, 'wechat_qr_renew.png')
    img.save(img_path)
    print(f'✅ QR码已保存: {img_path}')
    print(f'⚠ 有效期约35秒，请立即扫描!')
except urllib.error.HTTPError as e:
    print(f'❌ HTTP错误: {e.code} {e.reason}')
    print(f'   Body: {e.read().decode()[:200]}')
except Exception as e:
    print(f'❌ 错误: {e}')
