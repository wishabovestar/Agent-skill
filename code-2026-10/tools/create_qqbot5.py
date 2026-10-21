"""Create qqbot5 profile"""
import os, shutil, subprocess

src = "D:/hermes/hermes-data/profiles/qqbot4"
dst = "D:/hermes/hermes-data/profiles/qqbot5"

# Copy directory structure
shutil.copytree(src, dst, dirs_exist_ok=True)
print(f"✅ Copied {src} -> {dst}")

# Update .env - remove QQ credentials (user needs to provide new ones)
env_path = f"{dst}/.env"
with open(env_path) as f:
    lines = f.readlines()
new_lines = []
for line in lines:
    if line.startswith("QQ_APP_ID="):
        new_lines.append("# QQ_APP_ID=待填写\n")
    elif line.startswith("QQ_CLIENT_SECRET="):
        new_lines.append("# QQ_CLIENT_SECRET=待填写\n")
    else:
        new_lines.append(line)
with open(env_path, 'w') as f:
    f.writelines(new_lines)
print("✅ .env updated (QQ credentials cleared)")

# Clear gateway_state
import json
state_path = f"{dst}/gateway_state.json"
with open(state_path) as f:
    state = json.load(f)
state["pid"] = 0
state["platforms"] = {}
state["gateway_state"] = "created"
import datetime
state["updated_at"] = datetime.datetime.now().isoformat()
with open(state_path, 'w') as f:
    json.dump(state, f, indent=2)
print("✅ gateway_state cleared")

print(f"\n✅ qqbot5 创建完成!")
print(f"   路径: {dst}")
print(f"\n需要填写QQ Bot凭据:")
print(f"   1. 前往 https://q.qq.com/ (QQ开放平台)")
print(f"   2. 创建机器人应用 -> 获取 AppID 和 AppSecret")
print(f"   3. 填写到 {dst}/.env 中的 QQ_APP_ID= 和 QQ_CLIENT_SECRET=")
