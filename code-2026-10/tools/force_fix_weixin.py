"""
强制解决微信Token冲突 + 重新生成qqbot3二维码
"""
import subprocess, os, json, ssl, urllib.request, qrcode

# Step 1: Find and kill any gateway holding the WeChat token
print("=== Step 1: 释放Token ===")
# qqbot2 (PID 33368) is holding the token. 
# But it has weixin: enabled: false. The stale state is the issue.
# Clear the stale weixin state from qqbot2's gateway_state
state_path = "D:/hermes/hermes-data/profiles/qqbot2/gateway_state.json"
with open(state_path) as f:
    state = json.load(f)

# Remove weixin from platforms in the cached state
if "platforms" in state and "weixin" in state["platforms"]:
    del state["platforms"]["weixin"]
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)
    print("✅ Removed weixin from qqbot2 gateway_state")

# Step 2: Restart qqbot2 to release the token
subprocess.run(["hermes", "--profile", "qqbot2", "gateway", "run", "--replace"], 
               capture_output=True, timeout=30)
print("✅ qqbot2 restarted")

# Step 3: Regenerate QR for qqbot3
print("\n=== Step 2: 生成qqbot3二维码 ===")
TOKEN = open("D:/hermes/hermes-data/profiles/qqbot3/.env").read().split("WEIXIN_TOKEN=")[1].split("\n")[0].strip()

ctx = ssl._create_unverified_context()
url = "https://ilinkai.weixin.qq.com/ilink/bot/get_bot_qrcode?bot_type=3"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
data = json.loads(urllib.request.urlopen(req, context=ctx, timeout=15).read())
qr_url = data.get("qrcode_img_content", "")

qr = qrcode.QRCode(version=1, box_size=15, border=4)
qr.add_data(qr_url)
qr.make(fit=True)
img_path = "D:/hermes/data/wechat_qr_qqbot3.png"
qr.make_image(fill_color="black", back_color="white").save(img_path)

print(f"✅ QR saved: {img_path}")
print(f"🔗 {qr_url}")

# Step 4: Push to qqbot3 QQ (已关闭)
# subprocess.run(["hermes", "--profile", "qqbot3", "send", "-t", "qqbot",
#     f"📱 微信重新认证二维码\\n\\n请用微信扫描:\\n{qr_url}\\n\\n或打开文件: {img_path}\\n\\n⚠ 35秒有效,请尽快扫描!"],
#     capture_output=True, timeout=15)
# print("✅ QR pushed to qqbot3 QQ")
