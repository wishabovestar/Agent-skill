# -*- coding: utf-8 -*-
"""qqbot3 微信重新认证 — 生成QR + 轮询扫码 + 更新token"""
import qrcode, subprocess, json, time, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

QR_VAL = "7653b62ed1aea21886e04b0bdb657ffd"
BASE = "https://ilinkai.weixin.qq.com"
ENV_PATH = r"D:/hermes/hermes-data/profiles/qqbot3/.env"

# 1. 生成PNG
qr = qrcode.QRCode(version=2, box_size=8, border=3)
qr.add_data(QR_VAL)
qr.make(fit=True)
img = qr.make_image(fill_color="black", back_color="white")
img.save("D:/hermes/data/wechat_qr_qqbot3.png")
print("✅ PNG: D:/hermes/data/wechat_qr_qqbot3.png")

# 2. ASCII
qr2 = qrcode.QRCode(version=2, box_size=1, border=2)
qr2.add_data(QR_VAL)
qr2.make(fit=True)
qr2.print_ascii(invert=True)
print(f"\n🔗 {BASE}/ilink/bot/get_bot_qrcode?bot_type=3")
print(f"QR: {QR_VAL}")
print("等待扫码(60s)...")

# 3. 轮询
for i in range(30):
    try:
        r = subprocess.run(["curl","-s","--max-time","8",
            "-H","Content-Type: application/json",
            "-d", json.dumps({"qrcode": QR_VAL}),
            f"{BASE}/ilink/bot/get_qrcode_status?qrcode={QR_VAL}"],
            capture_output=True, timeout=12)
        data = json.loads(r.stdout) if r.stdout else {}
        ret = data.get("ret"); status = data.get("status")
        if ret == 0 and status == "confirmed":
            new_token = data.get("bot_token", "")
            print(f"\n✅ 扫码确认! (第{i+1}次)")
            if new_token:
                env = open(ENV_PATH, encoding='utf-8').read()
                lines = []
                for l in env.split('\n'):
                    if l.startswith('WEIXIN_TOKEN='):
                        lines.append(f"WEIXIN_TOKEN={new_token}")
                    else:
                        lines.append(l)
                open(ENV_PATH, 'w', encoding='utf-8').write('\n'.join(lines))
                print(f"  ✅ 新token已写入: {new_token[:40]}...")
                print(f"  重启gateway: hermes --profile qqbot3 gateway run --replace")
            else:
                print(f"  ⚠ 确认但无token: {data}")
            sys.exit(0)
        elif ret == 0 and status == "expired":
            print(f"  [{i+1}] QR过期, 重新获取...")
            r2 = subprocess.run(["curl","-s","--max-time","10",
                "-H","Content-Type: application/json","-d","{}",
                f"{BASE}/ilink/bot/get_bot_qrcode?bot_type=3"],
                capture_output=True, timeout=15)
            d2 = json.loads(r2.stdout) if r2.stdout else {}
            new_qr = d2.get("qrcode", "")
            if new_qr:
                print(f"  ✅ 新QR: {new_qr}")
        elif ret == -14:
            print(f"  [{i+1}] 等待扫码...")
        else:
            print(f"  [{i+1}] {json.dumps(data)[:80]}")
    except Exception as e:
        print(f"  [{i+1}] 异常: {e}")
    time.sleep(2)
print("\n⚠ 60s未扫码, 需重新运行")
