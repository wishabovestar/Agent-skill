"""Add agent-empathy to all profiles and platforms - FIXED"""
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
    
    ps = cfg.get('platform_skills', {})
    if not ps:
        print(f"[{profile}] ❌ No platform_skills")
        continue
    
    modified = False
    
    # Handle different nesting structures
    if 'default' in ps and isinstance(ps['default'], dict):
        # Structure: {default: {platform: "[...]"}}
        for plat, skills_str in ps['default'].items():
            if isinstance(skills_str, str):
                try:
                    skills = json.loads(skills_str)
                except:
                    continue
                if 'agent-empathy' not in skills:
                    skills.append('agent-empathy')
                    ps['default'][plat] = json.dumps(skills)
                    modified = True
                    print(f"[{profile}] default/{plat} ✅ added")
                else:
                    print(f"[{profile}] default/{plat} ✅ already there")
    else:
        # Structure: {platform: "[...]"}
        for plat, skills_str in ps.items():
            if isinstance(skills_str, str):
                try:
                    skills = json.loads(skills_str)
                except:
                    continue
                if 'agent-empathy' not in skills:
                    skills.append('agent-empathy')
                    ps[plat] = json.dumps(skills)
                    modified = True
                    print(f"[{profile}] {plat} ✅ added")
                else:
                    print(f"[{profile}] {plat} ✅ already there")
    
    if modified:
        shutil.copy2(config_path, bak_path)
        cfg['platform_skills'] = ps
        with open(config_path, 'w') as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        print(f"[{profile}] ✅ Saved (backup: {bak_path})")

print("\n✅ All profiles updated")
