"""
WeChat QR re-authentication - FIXED: single QR fetch, proper QR image save, Bearer token fixed
"""
import subprocess, json, os, time, re, sys

def qr_auth(profile):
    env_path = f"D:/hermes/hermes-data/profiles/{profile}/.env"
    with open(env_path) as f:
        env_data = f.read()
    
    def get_env(key):
        for line in env_data.split("\n"):
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
        return ""
    
    token = get_env("WEIXIN_TOKEN")
    base = get_env("WEIXIN_BASE_URL") or "https://ilinkai.weixin.qq.com"
    
    for round_num in range(4):
        # Get fresh QR code - single API call
        r = subprocess.run(
            ["curl", "-s", "--max-time", "10",
             "-H", f"Authorization: Bearer {token}",
             f"{base}/ilink/bot/get_bot_qrcode?bot_type=3"],
            capture_output=True, timeout=15
        )
        try:
            data = json.loads(r.stdout)
        except:
            print(f"❌ QR API: {r.stdout[:200]}")
            time.sleep(3)
            continue
            
        qr_url = data.get("qrcode_img_content", "")
        qr_val = data.get("qrcode", "")
        
        if not qr_url:
            print(f"❌ QR API error: {data}")
            continue
        
        print(f"\n{'='*55}")
        print(f"[{profile}] 第{round_num+1}/4次 - 请用微信扫描!")
        print(f"  {qr_url}")
        print(f"{'='*55}")
        
        # Save QR as PNG using qrcode library
        try:
            import qrcode as qrc
            qr_img = qrc.QRCode(version=1, box_size=10, border=4)
            qr_img.add_data(qr_url)
            qr_img.make(fit=True)
            qr_img.make_image(fill_color="black", back_color="white").save(
                f"D:/hermes/data/wechat_qr_{profile}.png")
            print(f"  ✅ QR: D:/hermes/data/wechat_qr_{profile}.png")
        except:
            print(f"  ⚠ QR image save skipped")
        
        # Poll for scan (60 seconds, 3s intervals)
        deadline = time.time() + 60
        dots = 0
        while time.time() < deadline:
            try:
                r3 = subprocess.run(
                    ["curl", "-s", "--max-time", "8",
                     "-H", f"Authorization: Bearer {token}",
                     f"{base}/ilink/bot/get_qrcode_status?qrcode={qr_val}"],
                    capture_output=True, timeout=12
                )
                raw = r3.stdout.strip()
                if not raw:
                    dots += 1
                    if dots % 15 == 0:
                        print("w", end="", flush=True)
                    time.sleep(3)
                    continue
                
                status_data = json.loads(raw)
                status = status_data.get("status", "wait")
                
                if status == "wait":
                    print(".", end="", flush=True)
                elif status == "scaned":
                    print("\n✅ Scanned! Confirm on phone...")
                elif status == "confirmed":
                    new_token = status_data.get("bot_token", "")
                    new_account = status_data.get("bot_account_id", "")
                    if new_token:
                        print(f"\n{'='*55}")
                        print(f"✅ AUTHENTICATION SUCCESS!")
                        print(f"  Token: {new_token[:40]}...")
                        print(f"  Account: {new_account}")
                        
                        new_env = env_data
                        if new_token != token:
                            new_env = new_env.replace(token, new_token)
                        if new_account:
                            new_env = re.sub(
                                r"^WEIXIN_ACCOUNT_ID=.*",
                                f"WEIXIN_ACCOUNT_ID={new_account}",
                                new_env, flags=re.MULTILINE
                            )
                        with open(env_path, "w") as f:
                            f.write(new_env)
                        print(f"  ✅ .env updated!")
                        return True
                    else:
                        print(f"\n⚠ No token in response")
                elif status == "expired":
                    print(f"\n⌛ QR expired")
                    break
                
                time.sleep(3)
            except Exception as e:
                dots += 1
                if dots % 15 == 0:
                    print("?", end="", flush=True)
                time.sleep(3)
        
        if round_num < 3:
            print(f"\n  Refreshing QR...")
    
    print(f"\n❌ Authentication failed")
    return False

if __name__ == "__main__":
    profile = sys.argv[1] if len(sys.argv) > 1 else "qqbot3"
    qr_auth(profile)
