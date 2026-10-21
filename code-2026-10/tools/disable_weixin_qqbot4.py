"""TODO-4: Disable WeChat on qqbot4 to resolve token conflict"""
import yaml, json, shutil, os

# Step 1: Disable weixin in config.yaml
config_path = "D:/hermes/hermes-data/profiles/qqbot4/config.yaml"
with open(config_path) as f:
    cfg = yaml.safe_load(f)

if 'platforms' not in cfg:
    cfg['platforms'] = {}
if 'weixin' not in cfg['platforms']:
    cfg['platforms']['weixin'] = {'enabled': False}
else:
    cfg['platforms']['weixin']['enabled'] = False

shutil.copy2(config_path, config_path + ".bak.tokenfix")
with open(config_path, 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
print("✅ qqbot4 config: weixin disabled")

# Step 2: Comment out WEIXIN_* in .env
env_path = "D:/hermes/hermes-data/profiles/qqbot4/.env"
with open(env_path, 'r') as f:
    lines = f.readlines()
new_lines = []
count = 0
for line in lines:
    if line.startswith("WEIXIN_") and not line.startswith("#WEIXIN_"):
        new_lines.append("#" + line)
        count += 1
    else:
        new_lines.append(line)
with open(env_path, 'w') as f:
    f.writelines(new_lines)
print(f"✅ qqbot4 .env: {count} WEIXIN_* lines commented")

# Step 3: Remove weixin from gateway_state
state_path = "D:/hermes/hermes-data/profiles/qqbot4/gateway_state.json"
if os.path.exists(state_path):
    with open(state_path) as f:
        state = json.load(f)
    removed = state.get("platforms", {}).pop("weixin", None)
    if removed:
        with open(state_path, 'w') as f:
            json.dump(state, f, indent=2)
        print("✅ qqbot4 state: weixin removed")
    else:
        print("ℹ️ qqbot4 state: no weixin entry")

print("\n✅ TODO-4 完成! 需要重启 qqbot4 gateway 生效")
