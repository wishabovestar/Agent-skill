# -*- coding: utf-8 -*-
"""qqbot3 微信认证 v3 — 大尺寸PNG + 从文件读QR + 120秒轮询"""
import qrcode, subprocess, json, time, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

QR_VAL = open(r"D:/hermes/data/qqbot3_qr_val.txt").read().strip()
BASE = "https://ilinkai.weixin.qq.com"
ENV_PATH = r"D:/hermes/hermes-data/profiles/qqbot3/.env"

print(f"轮询QR: {QR_VAL} (120秒)")

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
                print(f"  ✅ 新token已写入: {new_token[:45]}...")
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
