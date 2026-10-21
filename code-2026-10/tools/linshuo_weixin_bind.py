# -*- coding: utf-8 -*-
"""
linshuo 微信扫码绑定 — 轮询扫码状态, 成功后写入token并提示重启gateway
用法: python linshuo_weixin_bind.py <qrcode值>
"""
import subprocess, json, sys, time, os

QR_VAL = sys.argv[1] if len(sys.argv) > 1 else "25175726f1c55d8ca360be4501288ea7"
BASE = "https://ilinkai.weixin.qq.com"
ENV_PATH = r"D:/hermes/hermes-data/profiles/linshuo/.env"

print("="*60)
print("等待微信扫码绑定 (快速轮询, 2秒间隔)...")
print(f"QR: {QR_VAL}")
print("="*60)

for i in range(45):  # 45次 x 2s = 90s
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "8",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"qrcode": QR_VAL}),
             f"{BASE}/ilink/bot/get_qrcode_status?qrcode={QR_VAL}"],
            capture_output=True, timeout=12
        )
        data = json.loads(r.stdout) if r.stdout else {}
        ret = data.get("ret")
        status = data.get("status", data.get("errcode"))
        if ret == 0 and status == "confirmed":
            # 扫码确认
            new_token = data.get("bot_token", "")
            print(f"✅ 扫码确认! (第{i+1}次轮询)")
            if new_token:
                env = open(ENV_PATH, encoding='utf-8').read()
                lines = []
                for l in env.split('\n'):
                    if l.startswith('WEIXIN_TOKEN='):
                        lines.append(f"WEIXIN_TOKEN={new_token}")
                    else:
                        lines.append(l)
                open(ENV_PATH, 'w', encoding='utf-8').write('\n'.join(lines))
                print(f"  ✅ WEIXIN_TOKEN 已写入: {new_token[:40]}...")
                print(f"  重启gateway: hermes --profile linshuo gateway run --replace")
            else:
                print(f"  ⚠ 确认但未返回token: {data}")
            sys.exit(0)
        elif ret == 0 and status == "expired":
            # 二维码过期 → 自动重新生成并提示
            print(f"  [{i+1}] ⚠ 二维码已过期, 重新获取...")
            r2 = subprocess.run(
                ["curl", "-s", "--max-time", "10",
                 "-H", "Content-Type: application/json",
                 "-d", "{}",
                 f"{BASE}/ilink/bot/get_bot_qrcode?bot_type=3"],
                capture_output=True, timeout=15
            )
            try:
                d2 = json.loads(r2.stdout)
                new_qr = d2.get("qrcode", "")
                if new_qr:
                    QR_VAL = new_qr
                    url2 = d2.get("qrcode_img_content", "")
                    print(f"  ✅ 新二维码: {url2}")
                    print(f"  ⚠️ 请立即扫码! 或运行: python linshuo_qr_gen.py")
            except Exception as e:
                print(f"  ⚠ 重取二维码失败: {e}")
        elif ret == -14 or (status and "timeout" in str(status).lower()):
            print(f"  [{i+1}] 等待扫码中...")
        else:
            print(f"  [{i+1}] 状态: {json.dumps(data)[:100]}")
    except Exception as e:
        print(f"  [{i+1}] 轮询异常: {e}")
    time.sleep(2)

print("\n⚠ 60秒内未完成扫码, 二维码可能已过期。重新生成: python linshuo_qr_gen.py")
