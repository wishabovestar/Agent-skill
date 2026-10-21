"""Disable weixin in mybot config + restart"""
import yaml, shutil

config_path = 'D:/hermes/hermes-data/profiles/mybot/config.yaml'
bak_path = config_path + '.bak.noweixin'

with open(config_path) as f:
    cfg = yaml.safe_load(f)

# Add weixin: enabled: false to platforms
if 'platforms' not in cfg:
    cfg['platforms'] = {}

if 'weixin' not in cfg['platforms']:
    cfg['platforms']['weixin'] = {'enabled': False}
    print('✅ weixin disabled added')
else:
    cfg['platforms']['weixin']['enabled'] = False
    print('✅ weixin set to disabled')

shutil.copy2(config_path, bak_path)
with open(config_path, 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
print(f'✅ Saved (backup: {bak_path})')
