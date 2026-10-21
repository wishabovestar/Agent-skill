"""Generate WeChat QR code image and save to file"""
import requests, json, segno, os, sys

def get_qr(profile):
    env_path = f"D:/hermes/hermes-data/profiles/{profile}/.env"
    if not os.path.exists(env_path):
        print(f"❌ {profile}: 无.env")
        return None
    
    with open(env_path) as f:
        env = f.read()
    
    token = None
    base_url = "https://ilinkai.weixin.qq.com"
    for line in env.split("\n"):
        if line.startswith("WEIXIN_TOKEN="):
            token = line.split("=", 1)[1].strip()
        if line.startswith("WEIXIN_BASE_URL="):
            base_url = line.split("=", 1)[1].strip()
    
    if not token:
        print(f"❌ {profile}: 无WEIXIN_TOKEN")
        return None
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    # Call get_bot_qrcode API
    r = requests.post(
        f"{base_url}/ilink/bot/get_bot_qrcode",
        headers=headers,
        json={"bot_type": "3", "ttl": 300},
        timeout=15
    )
    
    print(f"  响应码: {r.status_code}")
    print(f"  响应头 Content-Type: {r.headers.get('Content-Type', '?')}")
    
    # Check if it returned image data
    ct = r.headers.get("Content-Type", "")
    if "image" in ct or "octet-stream" in ct:
        # Save image
        img_path = f"D:/hermes/data/wechat_qr_{profile}.png"
        with open(img_path, "wb") as f:
            f.write(r.content)
        print(f"  ✅ QR码已保存: {img_path}")
        print(f"  大小: {len(r.content)} bytes")
        return img_path
    else:
        # Try JSON
        try:
            data = r.json()
            print(f"  JSON响应: {json.dumps(data, indent=2)[:200]}")
            # Check for qrcode_url in response
            if "qrcode_url" in data:
                url = data["qrcode_url"]
                qr = segno.make(url)
                img_path = f"D:/hermes/data/wechat_qr_{profile}.png"
                qr.save(img_path, scale=10)
                print(f"  ✅ QR码已生成 (来自URL): {img_path}")
                return img_path
            elif "qr" in data:
                url = data["qr"]
                qr = segno.make(url)
                img_path = f"D:/hermes/data/wechat_qr_{profile}.png"
                qr.save(img_path, scale=10)
                print(f"  ✅ QR码已生成: {img_path}")
                return img_path
        except:
            print(f"  原始响应: {r.text[:200]}...")
    
    return None

if __name__ == "__main__":
    profile = sys.argv[1] if len(sys.argv) > 1 else "qqbot3"
    print(f"生成 {profile} 微信QR码...")
    path = get_qr(profile)
    if path:
        print(f"\n请使用微信扫描此二维码")
        print(f"文件: {path}")
    else:
        print(f"\n❌ 无法生成QR码")
