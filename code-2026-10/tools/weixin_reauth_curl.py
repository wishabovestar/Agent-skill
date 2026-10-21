"""
WeChat QR re-authentication using curl (Schannel SSL which works)
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
        # Step 1: Get fresh QR code
        r = subprocess.run(
            ["curl", "-s", "--max-time", "10",
             "-H", f"Authorization: Bearer {token}",
             f"{base}/ilink/bot/get_bot_qrcode?bot_type=3"],
            capture_output=True, timeout=15
        )
        data = json.loads(r.stdout)
        qr_url = data.get("qrcode_img_content", "")
        qr_val = data.get("qrcode", "")
        
        if not qr_url:
            print(f"❌ QR API error: {data}")
            return False
        
        print(f"\n{'='*55}")
        print(f"[{profile}] 第{round_num+1}/4次 - 请用微信扫描!")
        print(f"  Link: {qr_url}")
        print(f"{'='*55}")
        
        # Save as PNG
        r2 = subprocess.run(
            ["curl", "-s", "--max-time", "10",
             "-H", f"Authorization: Bearer {token}",
             "-o", f"D:/hermes/data/wechat_qr_{profile}.png",
             f"{base}/ilink/bot/get_bot_qrcode?bot_type=3"],
            capture_output=True, timeout=15
        )
        print(f"  ✅ QR saved: D:/hermes/data/wechat_qr_{profile}.png")
        
        # Step 2: Poll for scan (60 seconds, 3s intervals)
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                r3 = subprocess.run(
                    ["curl", "-s", "--max-time", "10",
                     "-H", f"Authorization: Bearer {token}",
                     f"{base}/ilink/bot/get_qrcode_status?qrcode={qr_val}"],
                    capture_output=True, timeout=15
                )
                status_data = json.loads(r3.stdout)
                status = status_data.get("status", "wait")
                ret = status_data.get("ret", 0)
                
                if ret != 0:
                    print(f"\n⚠ API error: {status_data}")
                    time.sleep(3)
                    continue
                
                if status == "wait":
                    print(".", end="", flush=True)
                elif status == "scaned":
                    print("\n✅ Scanned! Confirm on phone...")
                elif status == "confirmed":
                    new_token = status_data.get("bot_token", "")
                    new_account = status_data.get("bot_account_id", "")
                    if new_token:
                        print(f"\n{'='*55}")
                        print(f"✅ AUTHENTICATION SUCCESSFUL!")
                        print(f"  Token: {new_token[:40]}...")
                        print(f"  Account: {new_account}")
                        
                        # Update .env
                        new_env = env_data.replace(token, new_token)
                        if new_account:
                            new_env = re.sub(
                                r"^WEIXIN_ACCOUNT_ID=.*",
                                f"WEIXIN_ACCOUNT_ID={new_account}",
                                new_env, flags=re.MULTILINE
                            )
                        with open(env_path, "w") as f:
                            f.write(new_env)
                        print(f"  ✅ .env updated!")
                        print(f"\nRestart gateway: hermes --profile {profile} gateway run --replace")
                        return True
                    else:
                        print(f"\n⚠ Confirmed but no token in response: {status_data}")
                elif status == "expired":
                    print(f"\n⌛ QR expired...")
                    break
                
                time.sleep(3)
            except Exception as e:
                print(f"\n⚠ Poll error: {e}")
                time.sleep(3)
    
    print(f"\n❌ Authentication timed out after {round_num+1} attempts")
    return False

if __name__ == "__main__":
    profile = sys.argv[1] if len(sys.argv) > 1 else "qqbot3"
    qr_auth(profile)
