"""Add agent-empathy to all profiles and platforms"""
import yaml, json, shutil, os

profiles = ["mybot", "qqbot2", "qqbot3", "qqbot4"]

for profile in profiles:
    config_path = f"D:/hermes/hermes-data/profiles/{profile}/config.yaml"
    if not os.path.exists(config_path):
        print(f"[{profile}] ❌ No config.yaml")
        continue
    
    bak_path = config_path + ".bak.empathy"
    
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    
    if 'platform_skills' not in cfg or not cfg['platform_skills']:
        print(f"[{profile}] ❌ No platform_skills")
        continue
    
    modified = False
    for plat, skills_str in cfg['platform_skills'].items():
        if isinstance(skills_str, str):
            try:
                skills = json.loads(skills_str)
            except:
                skills = []
        else:
            skills = skills_str or []
        
        if 'agent-empathy' not in skills:
            skills.append('agent-empathy')
            cfg['platform_skills'][plat] = json.dumps(skills)
            modified = True
            print(f"[{profile}] {plat} ✅ agent-empathy added")
        else:
            print(f"[{profile}] {plat} ✅ already present")
    
    if modified:
        shutil.copy2(config_path, bak_path)
        with open(config_path, 'w') as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        print(f"[{profile}] ✅ Config saved (backup: {bak_path})")

print("\n✅ All profiles updated")
