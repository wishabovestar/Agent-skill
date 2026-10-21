"""
情感状态检测 — 用于触发心理Agent的情感疏导
集成到用户画像系统中，根据消息特征判断用户情绪状态
"""
import re
from collections import Counter

# 情感信号词汇
SENTIMENT_SIGNALS = {
    "positive": {
        "words": ["开心", "高兴", "太棒", "成功", "厉害", "感谢", "谢谢", "好极了",
                  "excellent", "great", "happy", "wonderful", "amazing", "perfect",
                  "满意", "进步", "突破", "喜悦"],
        "weight": 1.0,
    },
    "negative": {
        "words": ["难过", "沮丧", "失败", "烦", "累", "压力", "焦虑", "担心",
                  "sad", "tired", "stress", "anxious", "frustrated", "depressed",
                  "难受", "崩溃", "失落", "失望", "痛苦", "疲惫"],
        "weight": 2.0,  # 负面的权重更高，优先识别
    },
    "stress": {
        "words": ["加班", "熬夜", "太忙", "赶不上", "ddl", "deadline", "截止",
                  "崩溃", "扛不住", "受不了", "顶不住", "忙死了", "累死了",
                  "burnout", "overwhelmed", "exhausted"],
        "weight": 2.5,
    },
    "frustration": {
        "words": ["又失败", "还是不行", "什么鬼", "垃圾", "没用", "白做",
                  "frustrated", "useless", "waste", "stupid", "annoying",
                  "搞不定", "无语", "烦死了", "算了", "放弃"],
        "weight": 2.5,
    },
    "seeking_help": {
        "words": ["怎么办", "帮帮我", "求助", "help", "advice", "建议",
                  "能不能", "可以吗", "请教", "指导"],
        "weight": 1.5,
    },
}


def detect_emotion(text):
    """检测文本情感状态"""
    if not text:
        return {"emotion": "neutral", "intensity": 0, "should_empathize": False}
    
    text_lower = text.lower()
    scores = {}
    
    for category, signals in SENTIMENT_SIGNALS.items():
        score = 0
        for word in signals["words"]:
            matches = len(re.findall(re.escape(word.lower()), text_lower))
            score += matches * signals["weight"]
        if score > 0:
            scores[category] = score
    
    if not scores:
        return {"emotion": "neutral", "intensity": 0, "should_empathize": False}
    
    # 判断主导情绪
    dominant = max(scores, key=scores.get)
    intensity = min(scores[dominant] / 5.0, 1.0)  # 归一化到0-1
    
    # 触发共情条件
    should_empathize = (
        dominant in ["negative", "stress", "frustration"] or
        (dominant == "seeking_help" and intensity > 0.3)
    )
    
    return {
        "emotion": dominant,
        "intensity": round(intensity, 2),
        "scores": scores,
        "should_empathize": should_empathize,
    }


def get_empathy_strategy(emotion, intensity):
    """根据情感状态获取共情策略"""
    strategies = {
        "positive": {
            "action": "积极共鸣",
            "tone": "温暖鼓励",
            "example": "太好了！这个进展真不错，继续加油！",
        },
        "negative": {
            "action": "共情倾听",
            "tone": "温柔理解",
            "example": "听起来这段时间确实不容易，我在这里陪着你。",
        },
        "stress": {
            "action": "减压疏导",
            "tone": "安抚支持",
            "example": "压力大的时候记得适当休息，保持良好的节奏更重要。",
        },
        "frustration": {
            "action": "接纳肯定",
            "tone": "耐心包容",
            "example": "遇到这种情况确实会让人沮丧，但每一次尝试都有价值。",
        },
        "seeking_help": {
            "action": "积极回应",
            "tone": "认真务实",
            "example": "这个问题我可以帮忙一起分析，具体情况是怎样的？",
        },
    }

    if "neutral" not in strategies:
        strategies["neutral"] = {
            "action": "常规回应",
            "tone": "自然友好",
            "example": "明白了。",
        }
    
    strategy = strategies.get(emotion, strategies["neutral"])
    strategy["intensity"] = intensity
    return strategy


# 测试
if __name__ == "__main__":
    test_msgs = [
        "太棒了！实验终于成功了",
        "最近压力好大，项目赶不上进度",
        "又失败了，试了好多次都不行",
        "这个方向应该怎么继续？",
        "今天好累，加班到凌晨",
        "请帮我看看这个参数设置",
    ]
    for msg in test_msgs:
        result = detect_emotion(msg)
        strategy = get_empathy_strategy(result["emotion"], result["intensity"])
        print(f"消息: {msg}")
        print(f"  情感: {result['emotion']} (强度: {result['intensity']})")
        print(f"  共情: {'✅' if result['should_empathize'] else '❌'}")
        print(f"  策略: {strategy['action']}")
        print()
