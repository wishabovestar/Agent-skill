#!/usr/bin/env python3
"""
画像增强日更新脚本 — user_profiler.py v2.0 的增强包装器
新增: 
  (Phase 2) 情感分析 + 语义话题聚类 + 响应风格回溯
  (Phase 1) 数据质量修复

依赖: sentence-transformers, transformers, scipy
"""

import sys, os, json, time, re, sqlite3
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timedelta

# ── 配置 ──
PROFILES_DIR = Path("D:/hermes/profiles/user_profiles")
PROFILES_DIR.mkdir(parents=True, exist_ok=True)

# 惰性解析 session DB（函数先定义后调用）
_SESSION_DB = None

def find_session_db() -> Path:
    """自动检测session DB路径，依次检查:
    1. HERMES_PROFILE 环境变量
    2. 常见profile名: qqbot3, mybot, qqbot2, default
    """
    global _SESSION_DB
    if _SESSION_DB is not None:
        return _SESSION_DB
    profile = os.environ.get("HERMES_PROFILE", "")
    candidates = [profile] if profile else []
    candidates += ["qqbot3", "mybot", "qqbot2", "default"]
    for p in candidates:
        if not p:
            continue
        db = Path.home() / f"AppData/Local/hermes/profiles/{p}/state.db"
        if db.exists():
            print(f"  📁 Session DB detected: {db} (profile={p})")
            _SESSION_DB = db
            return db
    # fallback
    fallback = Path.home() / "AppData/Local/hermes/profiles/qqbot3/state.db"
    print(f"  ⚠️  Session DB not found via HERMES_PROFILE, using fallback: {fallback}")
    _SESSION_DB = fallback
    return fallback


SESSION_DB = find_session_db()


# ── 停用词过滤 ──
ENGLISH_STOPWORDS = {
    "a","an","the","and","or","but","if","in","on","at","to","for","of","with","by",
    "from","as","is","it","its","this","that","these","those","was","were","be","been",
    "have","has","had","do","does","did","will","would","could","should","may","might",
    "shall","can","need","dare","ought","used","i","you","he","she","we","they","me",
    "my","your","his","her","its","our","their","am","are","being","having","doing",
    "saying","getting","making","going","no","not","nor","so","up","out","about",
    "just","also","very","too","only","more","most","some","any","each","every","all",
    "both","few","many","much","such","same","other","another","into","through",
    "during","before","after","above","below","between","under","over","again",
    "further","then","once","here","there","where","when","why","how","what","which",
    "who","https","http","www","com","org","io","cn","net",
}


def _is_chinese_dominant(text: str, threshold: float = 0.15) -> bool:
    """判断文本是否以中文为主"""
    if not text:
        return False
    cjk_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return (cjk_chars / max(len(text), 1)) >= threshold

# ── 语义嵌入 (惰性加载) ──
_encoder = None
def get_encoder():
    global _encoder
    if _encoder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _encoder = SentenceTransformer("all-MiniLM-L6-v2")
        except ImportError:
            print("  ⚠️ sentence-transformers not installed, skipping semantic embedding")
    return _encoder

# ── 情感分析 (惰性加载) ──
_sentiment_pipeline = None
def get_sentiment_pipeline():
    global _sentiment_pipeline
    if _sentiment_pipeline is None:
        try:
            from transformers import pipeline
            _sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model="lxyuan/distilbert-base-multilingual-cased-sentiments-student",
            )
        except ImportError:
            print("  ⚠️ transformers not installed, skipping sentiment analysis")
    return _sentiment_pipeline

# ── 修复版话题提取（去停用词） ──
CJK_PATTERN = re.compile(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{2,}')

def extract_topics(content: str) -> list[str]:
    """提取关键词，过滤英文停用词和中英文混搭噪音（P0-2修复：中文主导时才过滤英文词）"""
    words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{2,}', content)
    is_cjk = _is_chinese_dominant(content)
    result = []
    for w in words:
        wl = w.lower()
        if wl.isdigit() or len(wl) < 2:
            continue
        # 中文主导时过滤英文停用词
        if is_cjk and wl in ENGLISH_STOPWORDS:
            continue
        if wl in ("https","http","www","com","org","io","cn","net"):
            continue
        result.append(wl)
    return result

# ── 修复版消息长度存储 ──
def compute_length_stats(lengths: list[int]) -> dict:
    """从原始长度列表计算统计量，而不是逐条存储"""
    if not lengths:
        return {"avg": 0, "max": 0, "min": 0, "count": 0, "p50": 0, "p95": 0}
    sorted_l = sorted(lengths)
    n = len(sorted_l)
    return {
        "avg": round(sum(sorted_l) / n, 1),
        "max": sorted_l[-1],
        "min": sorted_l[0],
        "count": n,
        "p50": sorted_l[n // 2],
        "p95": sorted_l[int(n * 0.95)],
    }

# ── 情感分析 ──
EMOTION_KEYWORDS = {
    "frustrated": ["烦", "气", "不行", "又", "还是错", "不对"],
    "urgent": ["急", "快", "立刻", "马上", "今天", "deadline"],
    "satisfied": ["好", "谢谢", "可以", "不错", "完美", "对"],
    "questioning": ["为什么", "怎么", "难道", "是不是", "是否"],
    "confused": ["不懂", "不明白", "什么意思", "什么"],
}

def analyze_sentiment(msg: str) -> dict:
    """情感分析 + 情绪关键词"""
    pipe = get_sentiment_pipeline()
    result = {"label": "NEUTRAL", "score": 0.5, "emotions": {}}
    if pipe:
        try:
            r = pipe(msg[:512])[0]
            result["label"] = r["label"]
            result["score"] = round(r["score"], 3)
        except Exception:
            pass
    
    # 情绪关键词检测
    emotions = {}
    for emotion, keywords in EMOTION_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in msg)
        if count > 0:
            emotions[emotion] = count
    if emotions:
        result["emotions"] = dict(Counter(emotions).most_common(3))
    
    return result

# ── 增强版 update_profile ──
def enhanced_update(platform: str, user_id: str, session_messages: list):
    """增强版 update_profile，修复P0问题+新增Phase2特征"""
    # 复用原 profiler 的核心逻辑（引入后覆盖）
    from user_profiler import analyze_session_messages, load_profile, save_profile
    from user_profiler import merge_sequence_into_profile, merge_decay_into_profile

    profile = load_profile(platform, user_id)
    analysis = analyze_session_messages(session_messages)

    if analysis["msg_count"] == 0:
        return profile

    # ── Phase 1 修复 ──

    # 1. 用修复版话题抽取替代原始提取
    corrected_topics = Counter()
    for msg in session_messages:
        if msg.get("role") != "user":
            continue
        for word in extract_topics(msg.get("content", "")):
            corrected_topics[word] += 1
    
    # 合并到画像（覆盖旧 topics）
    for topic, count in corrected_topics.items():
        profile["topics"][topic] = profile["topics"].get(topic, 0) + count
    profile["topics"] = dict(Counter(profile["topics"]).most_common(50))

    # 2. 修复消息长度存储 → 分位数截断 + 只存统计值
    raw_lengths = analysis["msg_lengths"]
    # 截断超过2000字符的极端URL/代码
    filtered_lengths = [min(l, 2000) for l in raw_lengths]
    all_lengths = profile.get("_raw_msg_lengths", []) + filtered_lengths
    profile["total_messages"] = profile.get("total_messages", 0) + analysis["msg_count"]
    profile["avg_msg_len_stats"] = compute_length_stats(all_lengths)
    profile["_raw_msg_lengths"] = all_lengths[-500:]  # 保留最近500条原始值（用于重算）

    # 保留原有风格/活跃/会话统计
    for style, count in analysis["style"].items():
        profile["style"][style] = profile["style"].get(style, 0) + count
    for h in analysis["hours"]:
        profile["active_hours"][str(h)] = profile["active_hours"].get(str(h), 0) + 1
    for d in analysis["days"]:
        profile["active_days"][str(d)] = profile["active_days"].get(str(d), 0) + 1
    profile["total_sessions"] += 1
    profile["last_seen"] = time.time()
    if profile["first_seen"] is None:
        profile["first_seen"] = time.time()

    # ── Phase 2 增强 ──
    
    # 3. 情感分析（聚合所有用户消息）
    sentiment_scores = []
    emotion_counts = Counter()
    for msg in session_messages:
        if msg.get("role") != "user":
            continue
        sa = analyze_sentiment(msg.get("content", ""))
        sentiment_scores.append(sa["score"] if sa["label"] == "POSITIVE" else (1 - sa["score"]) * 0.5)
        for em, cnt in sa.get("emotions", {}).items():
            emotion_counts[em] += cnt

    # 合并到画像
    existing_sent = profile.get("sentiment", {})
    pos_count = existing_sent.get("positive_count", 0) + sum(1 for s in sentiment_scores if s > 0.55)
    neg_count = existing_sent.get("negative_count", 0) + sum(1 for s in sentiment_scores if s < 0.45)
    total_seen = existing_sent.get("total_sentiment_samples", 0) + len(sentiment_scores)
    profile["sentiment"] = {
        "positive_ratio": round(pos_count / max(total_seen, 1), 3),
        "negative_ratio": round(neg_count / max(total_seen, 1), 3),
        "positive_count": pos_count,
        "negative_count": neg_count,
        "total_sentiment_samples": total_seen,
    }
    existing_emotions = existing_sent.get("emotion_keywords", {})
    for em, cnt in emotion_counts.items():
        existing_emotions[em] = existing_emotions.get(em, 0) + cnt
    profile["sentiment"]["emotion_keywords"] = dict(
        Counter(existing_emotions).most_common(10))

    # 4. 序列追踪 (复用v2.0逻辑)
    merge_sequence_into_profile(profile, analysis)
    merge_decay_into_profile(profile, analysis, 7)

    # 5. 偏好更新
    _update_enhanced_preferences(profile)

    # 清理旧格式
    if "avg_msg_len" in profile and isinstance(profile.get("avg_msg_len"), list):
        del profile["avg_msg_len"]  # 移除旧版逐条存储
    if "growth_history" in profile and profile.get("growth_history") == []:
        pass  # 保留空结构

    save_profile(profile)
    return profile


def _update_enhanced_preferences(profile: dict):
    """增强版偏好推断"""
    pref = profile["response_preferences"]
    msgs = profile["total_messages"]
    if msgs <= 5:
        return

    style = profile.get("style", {})
    total_style = sum(style.values()) or 1
    
    tech_ratio = style.get("technical", 0) / total_style
    casual_ratio = style.get("casual", 0) / total_style
    detailed_ratio = style.get("detailed", 0) / total_style
    
    pref["prefers_technical_depth"] = tech_ratio > 0.25
    pref["prefers_conciseness"] = casual_ratio > 0.35
    pref["prefers_detailed_explanation"] = detailed_ratio > 0.25
    pref["style_dominance"] = max(style, key=style.get) if style else "neutral"

    # 从情感数据推积极度
    sentiment = profile.get("sentiment", {})
    if sentiment.get("total_sentiment_samples", 0) >= 10:
        pref["user_satisfaction_trend"] = "positive" if sentiment.get("positive_ratio", 0.5) > 0.6 else "neutral"


def batch_enhanced_update(days: int = 7):
    """批量增强更新入口"""
    from user_profiler import scan_recent_sessions, CURRENT_PROFILE
    print(f"📊 画像增强更新 v2.5 (扫描最近{days}天)")
    print(f"   会话DB: {SESSION_DB}")
    print(f"   Profile: {CURRENT_PROFILE}")

    user_sessions = scan_recent_sessions(days)
    print(f"   发现 {len(user_sessions)} 个用户会话流")

    for user_key, messages in user_sessions.items():
        try:
            platform, user_id = user_key.split(":", 1)
            profile = enhanced_update(platform, user_id, messages)
            if profile.get("sentiment", {}).get("total_sentiment_samples", 0) > 0:
                sent_status = f"   😊 pos:{profile['sentiment']['positive_ratio']:.0%}"
            else:
                sent_status = ""
            print(f"   ✅ {platform}:{user_id[:20]} → {profile['total_messages']}条{sent_status}")
        except Exception as e:
            print(f"   ⚠️ {user_key[:30]} → 失败: {e}")
            import traceback; traceback.print_exc()

    from user_profiler import list_all_users
    print(f"\n   所有画像已更新 -> {PROFILES_DIR}")
    return list_all_users()


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    batch_enhanced_update(days)
