# -*- coding: utf-8 -*-
"""qqbot3 微信认证 v2 — 固定QR + 120秒长轮询"""
import qrcode, subprocess, json, time, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

QR_VAL = "ec8aae84d573029acaa76b2a3dcf69e0"
BASE = "https://ilinkai.weixin.qq.com"
ENV_PATH = r"D:/hermes/hermes-data/profiles/qqbot3/.env"

# PNG
qr = qrcode.QRCode(version=2, box_size=8, border=3)
qr.add_data(QR_VAL)
qr.make(fit=True)
qr.make_image(fill_color="black", back_color="white").save("D:/hermes/data/wechat_qr_qqbot3.png")

# ASCII
qr2 = qrcode.QRCode(version=2, box_size=1, border=2)
qr2.add_data(QR_VAL)
qr2.make(fit=True)
qr2.print_ascii(invert=True)
print(f"\n🔗 {QR_VAL}")
print(f"等待扫码(120s)...")

found = False
for i in range(60):
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
            else:
                print(f"  ⚠ 确认但无token: {data}")
            found = True
            break
        elif ret == 0 and status == "expired":
            print(f"  [{i+1}] QR过期")
            break
        elif i % 5 == 0:
            print(f"  [{i+1}] 等待扫码 ({status or data.get('errcode','?')})...")
    except Exception as e:
        if i % 5 == 0: print(f"  [{i+1}] 异常: {e}")
    time.sleep(2)

if not found:
    print("\n⚠ 120s未扫码")
