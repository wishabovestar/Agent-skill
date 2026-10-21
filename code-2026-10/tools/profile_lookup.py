"""画像感知助手 — 根据画像调整回复风格（P0-4修复: 兼容dict/list双格式）"""
import json, sys, os
from pathlib import Path
from collections import Counter

PROFILES = Path("D:/hermes/profiles/user_profiles")


def _safe_top_topics(topics, n=5) -> list:
    """兼容topics为dict或list格式"""
    if isinstance(topics, dict):
        return [t[0] for t in Counter(topics).most_common(n)]
    elif isinstance(topics, list):
        if topics and isinstance(topics[0], (list, tuple)):
            # [(topic, count), ...]
            return [t[0] for t in topics[:n]]
        else:
            return [str(t) for t in topics[:n]]
    return []


def _safe_avg_msg_len(p: dict) -> int:
    """兼容avg_msg_len(旧版list)和avg_msg_len_stats(新版dict)"""
    if "avg_msg_len_stats" in p and isinstance(p["avg_msg_len_stats"], dict):
        stats = p["avg_msg_len_stats"]
        return int(stats.get("p50", stats.get("avg", 120)))
    if "avg_msg_len" in p and isinstance(p["avg_msg_len"], list) and p["avg_msg_len"]:
        raw = p["avg_msg_len"]
        return int(sum(raw) / len(raw))
    return 120


def lookup(platform: str, user_id: str) -> dict:
    """查找用户画像，返回建议的回复调整参数"""
    safe_id = user_id.replace("<","_").replace(">","_").replace(":","_")
    # 先试精确匹配
    path = PROFILES / f"{platform}_{safe_id}.json"
    if not path.exists():
        # 再用模糊匹配（找前缀匹配的文件）
        for f in PROFILES.glob(f"{platform}_*.json"):
            if f.stem.replace(f"{platform}_", "").startswith(safe_id[:20]):
                path = f
                break
    if not path.exists():
        return {"profile_exists": False, "adjustments": {}}
    
    p = json.loads(path.read_text(encoding="utf-8"))
    msgs = p.get("total_messages", 0)
    if msgs < 3:
        return {"profile_exists": True, "status": "too_few_messages", "adjustments": {}}
    
    style = p.get("style", {})
    total_style = sum(style.values()) or 1
    
    # 计算风格占比
    style_pct = {k: v/total_style for k,v in style.items()}
    
    # 活跃时段
    hours = {int(k):v for k,v in p.get("active_hours",{}).items()}
    peak_hour = max(hours, key=hours.get) if hours else None
    
    # 平均消息长度（兼容新旧格式）
    avg_len = _safe_avg_msg_len(p)
    
    # 话题关键词（兼容list/dict）
    top_topics = _safe_top_topics(p.get("topics", {}), 5)
    
    # 生成调整参数
    adjustments = {
        "style": max(style_pct, key=style_pct.get) if style_pct else "neutral",
        "technical_depth": style_pct.get("technical", 0) > 0.3,
        "conciseness": style_pct.get("casual", 0) > 0.3,
        "peak_hour": peak_hour,
        "avg_msg_len": avg_len,
        "total_messages": msgs,
        "top_topics": top_topics,
    }
    
    return {"profile_exists": True, "status": "active", "adjustments": adjustments}


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        result = lookup(sys.argv[1], sys.argv[2])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("用法: python profile_lookup.py <platform> <user_id>")
        print("示例: python profile_lookup.py feishu oc_xxx")
