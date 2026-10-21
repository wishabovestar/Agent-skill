"""
Poll iLink API for QR scan result and capture token
"""
import json, subprocess, time, sys

QR_VALUE = "e0e60cb2ce0f424bdf4d38ade4ac3c4a"  # from last QR gen

def poll_qr_result():
    """Poll iLink to check if QR code was scanned"""
    for i in range(30):  # poll up to 30 times (5 min total)
        r = subprocess.run(
            'curl -s --max-time 10 '
            f'"https://ilinkai.weixin.qq.com/ilink/bot/get_bot_qrcode?bot_type=3&qrcode={QR_VALUE}"',
            shell=True, capture_output=True, text=True, timeout=15
        )
        try:
            data = json.loads(r.stdout)
        except:
            data = {}
        
        status = data.get("status", "")
        print(f"  [{i+1}/30] status={status}")

        # Check for success response containing token
        if data.get("ret") == 0:
            if "bot_token" in data or "token" in data:
                token = data.get("bot_token") or data.get("token", "")
                account = data.get("account_id") or data.get("wx_account", "")
                print(f"\n✅ 扫码成功!")
                print(f"WEIXIN_TOKEN={token}")
                print(f"WEIXIN_ACCOUNT_ID={account}")
                return {"token": token, "account_id": account}
        
        if status == "confirmed" or status == "scanned":
            print(f"  已扫码，等待确认...")
        
        time.sleep(10)
    
    print("\n❌ 超时，未检测到扫码")
    return None

if __name__ == "__main__":
    print("轮询iLink扫码结果...")
    result = poll_qr_result()
    if result:
        # Write to .env
        env_path = "D:/hermes/hermes-data/profiles/qqbot2/.env"
        with open(env_path, "a") as f:
            f.write(f"\n# WeChat (from QR scan)\n")
            f.write(f"WEIXIN_TOKEN={result['token']}\n")
            f.write(f"WEIXIN_ACCOUNT_ID={result['account_id']}\n")
            f.write(f"WEIXIN_BASE_URL=https://ilinkai.weixin.qq.com\n")
            f.write(f"WEIXIN_CDN_BASE_URL=https://novac2c.cdn.weixin.qq.com/c2c\n")
            f.write(f"WEIXIN_DM_POLICY=open\n")
        print(f"\n✅ 已写入 {env_path}")
        
        # Restart gateway
        print("\n重启 qqbot2 gateway...")
        subprocess.run(["hermes", "--profile", "qqbot2", "gateway", "stop"], capture_output=True, timeout=10)
        time.sleep(5)
        subprocess.run(["hermes", "--profile", "qqbot2", "gateway", "run", "--replace"], capture_output=True, timeout=30)
        print("✅ gateway 已启动")
