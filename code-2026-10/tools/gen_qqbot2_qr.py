"""
Generate WeChat QR code for qqbot2 profile
"""
import json, subprocess, sys
from pathlib import Path

# Step 1: Get QR code from iLink API (no auth needed for initial QR)
r = subprocess.run(
    'curl -s --max-time 10 -H "Content-Type: application/json" '
    '"https://ilinkai.weixin.qq.com/ilink/bot/get_bot_qrcode?bot_type=3"',
    shell=True, capture_output=True, text=True, timeout=15
)

data = json.loads(r.stdout)
if data.get("ret") != 0:
    print(f"Error: {data}")
    sys.exit(1)

qr_value = data["qrcode"]
qr_img_url = data["qrcode_img_content"]
print(f"QR value: {qr_value}")
print(f"QR URL: {qr_img_url}")

# Step 2: Try to generate QR image using segno or qrcode
try:
    import segno
    qr = segno.make(qr_img_url)
    output = str(Path.home() / "AppData/Local/hermes/qqbot2_wechat_qr.png")
    qr.save(output, scale=10)
    print(f"QR saved to: {output}")
    print(f"MEDIA:{output}")
except ImportError:
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_img_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        output = str(Path.home() / "AppData/Local/hermes/qqbot2_wechat_qr.png")
        img.save(output)
        print(f"QR saved to: {output}")
        print(f"MEDIA:{output}")
    except ImportError:
        print(f"QR code URL: {qr_img_url}")
        print("(install segno or qrcode to generate image file)")

print(f"\n⚠ QR码仅35秒有效，请立即发送给用户扫描!")
print(f"扫描后需将新Token写入 qqbot2 .env")
print(f"WEIXIN_TOKEN=<new_token>")
print(f"WEIXIN_ACCOUNT_ID=<new_account_id>")
