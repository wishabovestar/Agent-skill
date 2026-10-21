"""
Update qqbot2 config for physics/ceramics agent integration
"""
import yaml, shutil
from datetime import datetime

config_path = "D:/hermes/hermes-data/profiles/qqbot2/config.yaml"
bak_path = config_path + "." + datetime.now().strftime("%Y%m%d_%H%M%S") + ".bak"

# Backup
shutil.copy2(config_path, bak_path)
print(f"✅ Backup: {bak_path}")

with open(config_path, encoding="utf-8") as f:
    config = yaml.safe_load(f)

# Update platform_skills to include xuntian for physics/ceramics research
config.setdefault("platform_skills", {}).setdefault("default", {})
config["platform_skills"]["default"]["weixin"] = '["hot-load-dispatcher", "unified-skill-registry", "profile-aware", "difficulty-triage", "xuntian-github-scout"]'

# Add knowledge base config
config["knowledge"] = {
    "physics_knowledge": "D:/hermes/data/physics_knowledge",
    "book_knowledge": "D:/hermes/data/book_knowledge",
    "math_knowledge": "D:/hermes/data/math_knowledge",
}

with open(config_path, "w", encoding="utf-8") as f:
    yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print("✅ Config updated with physics/ceramics agent integration")
print("   - xuntian-github-scout added to weixin platform_skills")
print("   - knowledge base paths configured")
