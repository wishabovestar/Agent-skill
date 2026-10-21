"""
WeChat QR re-authentication with PNG save and polling
Usage: python weixin_reauth.py qqbot3
"""
import json, ssl, urllib.request, qrcode, os, sys, time

def reauth(profile):
    env_path = f"D:/hermes/hermes-data/profiles/{profile}/.env"
    with open(env_path) as f:
        env = {}
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    
    token = env.get("WEIXIN_TOKEN", "")
    base = env.get("WEIXIN_BASE_URL", "https://ilinkai.weixin.qq.com")
    
    ctx = ssl._create_unverified_context()
    
    for refresh in range(4):
        # Get fresh QR code
        req = urllib.request.Request(
            f"{base}/ilink/bot/get_bot_qrcode?bot_type=3",
            headers={"Authorization": f"Bearer {token}"}
        )
        resp = urllib.request.urlopen(req, context=ctx, timeout=15)
        data = json.loads(resp.read())
        
        qr_url = data.get("qrcode_img_content", "")
        qr_val = data.get("qrcode", "")
        if not qr_url:
            print(f"❌ QR API错误: {data}")
            return False
        
        print(f"\n{'='*50}")
        print(f"[{profile}] 第{refresh+1}次QR码 - 请用微信扫描!")
        print(f"  链接: {qr_url}")
        print(f"{'='*50}")
        
        # Save as PNG
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_url)
        qr.make(fit=True)
        img_path = f"D:/hermes/data/wechat_qr_{profile}.png"
        qr.make_image(fill_color="black", back_color="white").save(img_path)
        print(f"  ✅ PNG: {img_path}")
        
        # Show as ASCII art
        qr_ascii = qrcode.QRCode(version=1, box_size=2, border=1)
        qr_ascii.add_data(qr_url)
        qr_ascii.make(fit=True)
        qr_ascii.print_ascii(invert=True)
        print()
        
        # Poll for scan status (35 seconds, checking every 2s)
        deadline = time.time() + 35
        while time.time() < deadline:
            try:
                status_req = urllib.request.Request(
                    f"{base}/ilink/bot/get_qrcode_status?qrcode={qr_val}",
                    headers={"Authorization": f"Bearer {token}"}
                )
                status_resp = urllib.request.urlopen(status_req, context=ctx, timeout=5)
                status_data = json.loads(status_resp.read())
                status = status_data.get("status", "wait")
                
                if status == "wait":
                    print(".", end="", flush=True)
                elif status == "scaned":
                    print("\n✅ 已扫码! 请在手机上点击确认...")
                    # Continue polling for confirmation
                elif status == "confirmed":
                    print("\n✅ 已确认!")
                    # Get new token from response
                    new_token = status_data.get("bot_token", "")
                    new_account = status_data.get("bot_account_id", "")
                    if new_token:
                        # Update .env
                        with open(env_path, "r") as f:
                            env_content = f.read()
                        env_content = env_content.replace(token, new_token)
                        if new_account:
                            import re
                            env_content = re.sub(
                                r"^WEIXIN_ACCOUNT_ID=.*",
                                f"WEIXIN_ACCOUNT_ID={new_account}",
                                env_content, flags=re.MULTILINE
                            )
                        with open(env_path, "w") as f:
                            f.write(env_content)
                        print(f"✅ Token已更新! 重启gateway即可")
                        return True
                elif status == "expired":
                    print("\n⌛ QR码过期...")
                    break
                
                time.sleep(2)
            except Exception as e:
                print(f"\n⚠ 轮询错误: {e}")
                time.sleep(2)
        
        if refresh < 3:
            print(f"\n  刷新QR码 ({refresh+1}/3)...")
    
    print("\n❌ 认证超时")
    return False

if __name__ == "__main__":
    profile = sys.argv[1] if len(sys.argv) > 1 else "qqbot3"
    reauth(profile)
