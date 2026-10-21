"""Clone qqbot2 weixin config to qqbot4 qqbot platform"""
import yaml, json, shutil

config_path = 'D:/hermes/hermes-data/profiles/qqbot4/config.yaml'
bak_path = config_path + '.bak.' + __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
shutil.copy2(config_path, bak_path)

with open(config_path) as f:
    cfg = yaml.safe_load(f)

# Set platform_skills for qqbot (same as qqbot2 weixin)
cfg['platform_skills'] = {
    'qqbot': '["hot-load-dispatcher", "unified-skill-registry", "profile-aware", "difficulty-triage", "xuntian-github-scout", "agent-cluster-orchestrator", "algorithm-architect", "pdf-reader", "3d-model-agent"]'
}

# Set platform_toolsets for qqbot
cfg['platform_toolsets'] = {
    'cli': '["clarify","cronjob","delegation","file","memory","session_search","skills","terminal","todo","web","tts","browser","computer_use","vision","image_gen"]',
    'qqbot': '["terminal", "file", "web", "delegation", "cronjob", "memory", "session_search", "clarify", "todo", "tts"]',
}

with open(config_path, 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

print('✅ qqbot4 config updated')
print(f'   Backup: {bak_path}')
print(f'   platform_skills.qqbot configured')
print(f'   platform_toolsets.qqbot configured')
