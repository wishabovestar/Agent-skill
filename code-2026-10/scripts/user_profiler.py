#!/usr/bin/env python3
"""User profile cron wrapper - calls the main profiler + 琢言心理学/情感分析."""
import sys, os, json
sys.path.insert(0, "D:/hermes/analysis")
from user_profiler import batch_update, list_all_users, generate_report, PROFILES_DIR, SESSION_DB

days = 7
users = batch_update(days)

# 琢言Agent: 心理学/情感维度分析
def analyze_psychology(profile):
    """分析用户消息中的心理和情感特征"""
    analysis = {
        "communication_style": "",     # 沟通风格: 直接/分析型/情感型/行动型
        "emotional_tone": "",          # 情感基调
        "decision_pattern": "",        # 决策模式
        "stress_response": "",         # 压力响应
        "learning_preference": "",     # 学习偏好
    }
    if not profile or profile.get("total_msgs", 0) < 5:
        return analysis
    
    # 基于消息长度和频率分析
    avg_len = profile.get("avg_msg_len", 0)
    active_hours = profile.get("active_hours", [])
    topics = profile.get("topics", [])
    
    if avg_len > 200:
        analysis["communication_style"] = "分析详细型"
        analysis["learning_preference"] = "深度技术阅读"
    elif avg_len > 80:
        analysis["communication_style"] = "平衡沟通型"
        analysis["learning_preference"] = "混合式学习"
    else:
        analysis["communication_style"] = "简洁行动型"
        analysis["learning_preference"] = "快速获取要点"
    
    # 基于主题分析
    tech_topics = [t for t in topics if any(k in t.lower() for k in ["电池","算法","代码","系统","网络"])]
    if len(tech_topics) > len(topics) * 0.6:
        analysis["emotional_tone"] = "理性技术型"
        analysis["decision_pattern"] = "数据驱动决策"
    else:
        analysis["emotional_tone"] = "均衡型"
        analysis["decision_pattern"] = "综合分析决策"
    
    # 活跃时段分析
    if active_hours:
        night = sum(1 for h in active_hours if h >= 22 or h < 6)
        if night > len(active_hours) * 0.3:
            analysis["stress_response"] = "深夜活跃型（高专注时段）"
        else:
            analysis["stress_response"] = "常规作息型"
    
    return analysis

# Build summary output
lines = [f"📊 用户画像每日更新（扫描最近{days}天）"]
lines.append(f"   会话DB: {SESSION_DB}")
lines.append(f"   存储: {PROFILES_DIR}")
lines.append("")

if not users:
    lines.append("   ⚠️ 暂无用户数据")
else:
    for u in sorted(users, key=lambda x: -x["total_msgs"]):
        lines.append(f"   👤 {u['platform']}:{u['user_id'][:24]} — {u['total_msgs']}条消息")
        
        # 心理/情感分析
        psy = analyze_psychology(u)
        if psy["communication_style"]:
            lines.append(f"      🧠 琢言分析:")
            lines.append(f"         沟通风格: {psy['communication_style']}")
            lines.append(f"         情感基调: {psy['emotional_tone']}")
            lines.append(f"         决策模式: {psy['decision_pattern']}")
            lines.append(f"         压力响应: {psy['stress_response']}")
            lines.append(f"         学习偏好: {psy['learning_preference']}")
        
        # 存储心理分析到画像
        profile_path = os.path.join(PROFILES_DIR, f"{u['platform']}_{u['user_id'][:32]}.json")
        if os.path.exists(profile_path):
            try:
                with open(profile_path, 'r', encoding='utf-8') as f:
                    pdata = json.load(f)
                pdata['psychology'] = psy
                with open(profile_path, 'w', encoding='utf-8') as f:
                    json.dump(pdata, f, ensure_ascii=False, indent=2)
            except: pass
    
    lines.append(f"\n   💡 琢言Agent心理/情感分析维度:")
    lines.append(f"      - 沟通风格: 简洁行动型/平衡沟通型/分析详细型")
    lines.append(f"      - 情感基调: 理性技术型/均衡型/情感导向型")
    lines.append(f"      - 心理画像已存储至用户画像JSON")
    lines.append(f"\n   共 {len(users)} 个用户")

print("\n".join(lines))
