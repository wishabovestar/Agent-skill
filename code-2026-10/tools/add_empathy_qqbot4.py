"""Add agent-empathy to qqbot4 config"""
import yaml, json, shutil

config_path = 'D:/hermes/hermes-data/profiles/qqbot4/config.yaml'
bak_path = config_path + '.bak.' + __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
shutil.copy2(config_path, bak_path)

with open(config_path) as f:
    cfg = yaml.safe_load(f)

# Add agent-empathy to qqbot platform_skills
if 'platform_skills' not in cfg:
    cfg['platform_skills'] = {}

current = cfg['platform_skills'].get('qqbot', '[]')
if isinstance(current, str):
    skills = json.loads(current)
else:
    skills = current or []

if 'agent-empathy' not in skills:
    skills.append('agent-empathy')

cfg['platform_skills']['qqbot'] = json.dumps(skills)

with open(config_path, 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

print(f'✅ agent-empathy added to qqbot4 qqbot platform')
print(f'   Skills: {skills}')
print(f'   Backup: {bak_path}')
