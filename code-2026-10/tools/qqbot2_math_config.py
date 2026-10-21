"""
Update qqbot2 config for math group agent integration
"""
import yaml, shutil
from datetime import datetime

config_path = "D:/hermes/hermes-data/profiles/qqbot2/config.yaml"
bak_path = config_path + "." + datetime.now().strftime("%Y%m%d_%H%M%S") + ".bak"
shutil.copy2(config_path, bak_path)
print(f"✅ Backup: {bak_path}")

with open(config_path, encoding="utf-8") as f:
    config = yaml.safe_load(f)

# Update platform_skills - add agent-cluster-orchestrator and algorithm-architect
config.setdefault("platform_skills", {}).setdefault("default", {})
config["platform_skills"]["default"]["weixin"] = (
    '["hot-load-dispatcher", "unified-skill-registry", "profile-aware", '
    '"difficulty-triage", "xuntian-github-scout", '
    '"agent-cluster-orchestrator", "algorithm-architect"]'
)

# Update knowledge paths (merge with existing)
config.setdefault("knowledge", {})
config["knowledge"].update({
    "math_knowledge": "D:/hermes/data/math_knowledge",
    "physics_knowledge": "D:/hermes/data/physics_knowledge",
    "book_knowledge": "D:/hermes/data/book_knowledge",
})

with open(config_path, "w", encoding="utf-8") as f:
    yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print("✅ Config updated with math group agent integration")
print("   - agent-cluster-orchestrator added (数学组通量/算渊/归藏/证道)")
print("   - algorithm-architect added (算法架构/复杂度分析)")
print("   - math_knowledge path configured")
