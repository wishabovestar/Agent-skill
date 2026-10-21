"""Disable weixin on qqbot2 + regenerate qqbot3 QR image"""
import yaml, shutil

# ===== 1. Disable weixin on qqbot2 =====
config_path = 'D:/hermes/hermes-data/profiles/qqbot2/config.yaml'
bak_path = config_path + '.bak.noweixin'

with open(config_path) as f:
    cfg = yaml.safe_load(f)

if 'platforms' not in cfg:
    cfg['platforms'] = {}
if 'weixin' not in cfg['platforms']:
    cfg['platforms']['weixin'] = {'enabled': False}
else:
    cfg['platforms']['weixin']['enabled'] = False

shutil.copy2(config_path, bak_path)
with open(config_path, 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

print('✅ qqbot2 weixin disabled in config')

# Also comment out WEIXIN_* in .env
env_path = 'D:/hermes/hermes-data/profiles/qqbot2/.env'
with open(env_path, 'r') as f:
    lines = f.readlines()
new_lines = []
for line in lines:
    if line.startswith('WEIXIN_') and not line.startswith('#WEIXIN_'):
        new_lines.append('#' + line)
    else:
        new_lines.append(line)
with open(env_path, 'w') as f:
    f.writelines(new_lines)
print('✅ qqbot2 WEIXIN_* commented in .env')
