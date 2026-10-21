"""
多用户画像系统 — User Profiler v2.0 (马卡洛夫预测链升级)
========================================================
v1.0: 统计摘要 → 被动匹配
v2.0: 序列追踪 → 主动预测

新增:
  - sequence.style_transition  风格转移矩阵
  - sequence.last_N_styles    最近N条消息的风格序列
  - sequence.hour_style_profile 各时段的风格分布
  - decay.last_7d/30d_*       时域衰减权重

输出: D:/hermes/profiles/user_profiles/<platform>_<user_id>.json
"""

import json, time, re, os, sqlite3
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from typing import Optional

# ── 配置 ──────────────────────────────────────────
PROFILES_DIR = Path("D:/hermes/profiles/user_profiles")
# 动态解析 session DB: 从环境变量 HERMES_PROFILE 获取当前 profile 名称
CURRENT_PROFILE = os.environ.get("HERMES_PROFILE", "qqbot3")
SESSION_DB = Path.home() / f"AppData/Local/hermes/profiles/{CURRENT_PROFILE}/state.db"
PROFILES_DIR.mkdir(parents=True, exist_ok=True)

MAX_ROLLING_STYLES = 30          # 保留最近30条消息风格
DECAY_WEIGHTS = {7: 0.5, 30: 0.3, 0: 0.2}  # 7天:50%, 30天:30%, 全部:20%

# ── 语言风格分析 ──────────────────────────────────
STYLE_MARKERS = {
    "formal": ["您好", "请问", "感谢", "恳请", "麻烦您", "是否", "建议"],
    "casual": ["哈喽", "嗨", "好嘞", "谢啦", "呗", "嘛", "行", "OK"],
    "technical": ["参数", "误差", "机理", "模型", "阈值", "效率", "曲线", "分析"],
    "urgent": ["急", "立刻", "马上", "快点", "尽快", "紧急", "赶紧"],
    "detailed": ["因为", "所以", "首先", "其次", "总结", "具体", "详细"],
}

# 简练vs啰嗦标记（用于消息长度风格预测）
BREVITY_MARKERS = {
    "concise": ["是", "否", "好", "嗯", "行", "ok", "OK"],
}
VERBOSE_THRESHOLD = 100  # 超过100字视为"详细"消息

# ── 停用词过滤（P0-2修复） ──────────────────────
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
    """判断文本是否以中文为主（中文CJK字符占比超过threshold）"""
    if not text:
        return False
    cjk_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return (cjk_chars / max(len(text), 1)) >= threshold

def _extract_topics_filtered(content: str) -> list[str]:
    """提取关键词并过滤英文停用词；仅当内容含足够中文时才过滤英文词"""
    # 分开匹配: 中文连续字 或 英文连续词
    tokens = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{2,}', content)
    is_cjk = _is_chinese_dominant(content)
    result = []
    for w in tokens:
        wl = w.lower()
        # 纯数字/无意义
        if wl.isdigit() or len(wl) < 2:
            continue
        # 中文主导时过滤英文停用词
        if is_cjk and wl in ENGLISH_STOPWORDS:
            continue
        # 过滤纯URL片段
        if wl in ("https","http","www","com","org","io","cn","net"):
            continue
        result.append(wl)
    return result

TIME_BUCKETS = {
    (0, 6): "深夜", (6, 9): "早晨", (9, 12): "上午",
    (12, 14): "午后", (14, 18): "下午", (18, 21): "傍晚", (21, 24): "夜间",
}


# ── 单条消息风格分类 ──────────────────────────────

def classify_message_style(content: str) -> tuple[str, float]:
    """
    对单条用户消息做风格分类，返回 (dominant_style, confidence)
    置信度 = 匹配标记数 / 最长可能标记数
    无匹配时返回 ("neutral", 0.0)
    """
    matched = {}
    for style, markers in STYLE_MARKERS.items():
        count = sum(1 for m in markers if m in content)
        if count > 0:
            matched[style] = count

    if not matched:
        return ("neutral", 0.0)

    # 消息长度辅助判断: 超长消息倾向 technical/detailed
    if len(content) > VERBOSE_THRESHOLD:
        matched["detailed"] = matched.get("detailed", 0) + 1
        # 如果内容含技术词，增强technical权重
        tech_count = sum(1 for m in STYLE_MARKERS["technical"] if m in content)
        if tech_count >= 2:
            matched["technical"] = matched.get("technical", 0) + 1

    dominant = max(matched, key=matched.get)
    max_possible = max(len(STYLE_MARKERS[s]) for s in matched)
    confidence = matched[dominant] / max_possible if max_possible > 0 else 1.0
    return (dominant, min(confidence, 1.0))


def build_style_sequence(messages: list[dict]) -> list[dict]:
    """
    按时间顺序扫描用户消息，返回风格序列：
    [{"style": "technical", "confidence": 0.6, "hour": 15, "length": 120}, ...]
    """
    seq = []
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        ts = msg.get("timestamp", 0)
        style, conf = classify_message_style(content)
        hour = datetime.fromtimestamp(ts if ts > 1e10 else ts).hour if ts else 12
        seq.append({
            "style": style,
            "confidence": round(conf, 2),
            "hour": hour,
            "length": len(content),
        })
    return seq


def build_transition_matrix(style_seq: list[str]) -> dict[str, dict[str, int]]:
    """
    从风格序列构建转移矩阵：
    {"technical": {"technical": 10, "casual": 3}, "casual": {...}}
    """
    matrix = defaultdict(lambda: defaultdict(int))
    for i in range(len(style_seq) - 1):
        from_s = style_seq[i]
        to_s = style_seq[i + 1]
        matrix[from_s][to_s] += 1
    return {k: dict(v) for k, v in matrix.items()}


def build_hour_profile(seq: list[dict]) -> dict[str, dict[str, int]]:
    """按小时统计风格分布: {"15": {"technical": 3, "casual": 1}}"""
    profile = defaultdict(lambda: defaultdict(int))
    for item in seq:
        h = str(item["hour"])
        profile[h][item["style"]] += 1
    return {h: dict(stats) for h, stats in profile.items()}


# ── 画像存储操作 ──────────────────────────────────

def _profile_path(platform: str, user_id: str) -> Path:
    safe_id = re.sub(r'[<>:"/\\|?*]', '_', user_id)[:64]
    return PROFILES_DIR / f"{platform}_{safe_id}.json"


def load_profile(platform: str, user_id: str) -> dict:
    """加载用户画像，不存在则返回空模板（v2.0含sequence结构）。"""
    p = _profile_path(platform, user_id)
    if p.exists():
        raw = json.loads(p.read_text(encoding="utf-8"))
        # v1.x → v2.0 迁移：补充缺失字段
        if "sequence" not in raw:
            raw["sequence"] = _empty_sequence()
        if "decay" not in raw:
            raw["decay"] = _empty_decay()
        if "correction_history" not in raw:
            raw["correction_history"] = []
        return raw
    return _empty_profile(platform, user_id)


def _empty_sequence() -> dict:
    return {
        "style_transition": {},
        "last_N_styles": [],
        "hour_style_profile": {},
        "last_update_session": 0,
    }


def _empty_decay() -> dict:
    return {
        "last_7d_style": {},
        "last_30d_style": {},
        "last_7d_topics": {},
    }


def _empty_profile(platform: str, user_id: str) -> dict:
    return {
        "platform": platform,
        "user_id": user_id,
        "first_seen": time.time(),
        "last_seen": None,
        "total_sessions": 0,
        "total_messages": 0,
        "style": {"formal": 0, "casual": 0, "technical": 0, "urgent": 0, "detailed": 0},
        "active_hours": {},
        "active_days": {},
        "topics": {},
        "avg_msg_len": [],
        "sequence": _empty_sequence(),
        "decay": _empty_decay(),
        "correction_history": [],
        "response_preferences": {
            "prefers_conciseness": None,
            "prefers_technical_depth": None,
            "common_needs": [],
        },
        "growth_history": [],
        "last_updated": None,
    }


def save_profile(profile: dict):
    p = _profile_path(profile["platform"], profile["user_id"])
    profile["last_updated"] = time.time()
    p.write_text(json.dumps(profile, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


# ── 会话分析 ──────────────────────────────────────

def analyze_session_messages(session_messages: list) -> dict:
    """
    分析单次会话中的用户消息。
    返回 v1.0 原有统计 + v2.0 风格序列+转移矩阵。
    """
    result = {
        "msg_count": 0,
        "style": Counter(),
        "topics": Counter(),
        "msg_lengths": [],
        "hours": [],
        "days": [],
        # v2.0 新增
        "style_sequence": [],       # [{"style": ..., "confidence": ..., "hour": ...}]
        "style_transition": {},     # 本次会话内的转移矩阵
        "hour_profile": {},         # 本次会话内的按小时风格分布
    }

    for msg in session_messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        ts = msg.get("timestamp", 0)

        if role != "user":
            continue
        result["msg_count"] += 1
        result["msg_lengths"].append(len(content))

        # 时间分析
        if ts:
            dt = datetime.fromtimestamp(ts if ts > 1e10 else ts)
            result["hours"].append(dt.hour)
            result["days"].append(dt.weekday())

        # v1.0 风格标记统计
        for style, markers in STYLE_MARKERS.items():
            for m in markers:
                if m in content:
                    result["style"][style] += 1

        # 话题关键词（P0-2修复：使用停用词过滤版）
        for kw in _extract_topics_filtered(content):
                result["topics"][kw.lower()] += 1

    # v2.0: 构建风格序列
    result["style_sequence"] = build_style_sequence(session_messages)
    style_labels = [s["style"] for s in result["style_sequence"]]
    if len(style_labels) >= 2:
        result["style_transition"] = build_transition_matrix(style_labels)
    result["hour_profile"] = build_hour_profile(result["style_sequence"])

    return result


def scan_recent_sessions(days: int = 7) -> dict:
    """扫描最近N天的会话数据，按平台+用户分组。"""
    user_sessions = defaultdict(list)

    if not SESSION_DB.exists():
        print(f"  ⚠️ Session DB not found: {SESSION_DB}")
        return user_sessions

    try:
        conn = sqlite3.connect(str(SESSION_DB))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff = (datetime.now() - timedelta(days=days)).timestamp()
        cursor.execute(
            "SELECT id, source, chat_id, chat_type, title, started_at, message_count "
            "FROM sessions WHERE started_at > ? AND source NOT IN ('cron','cli') "
            "ORDER BY started_at DESC",
            (cutoff,)
        )
        for row in cursor.fetchall():
            sid = row["id"]
            source = row["source"] or "unknown"
            chat_id = row["chat_id"] or f"anon_{sid[:8]}"
            chat_type = row["chat_type"]

            msg_cursor = conn.cursor()
            msg_cursor.execute(
                "SELECT role, content, timestamp FROM messages "
                "WHERE session_id = ? ORDER BY timestamp ASC",
                (sid,)
            )
            msgs = [dict(r) for r in msg_cursor.fetchall()]
            if not msgs:
                continue

            user_key = f"{source}:{chat_id}"
            user_sessions[user_key].extend(msgs)

        conn.close()
    except Exception as e:
        print(f"  ⚠️ Session DB scan error: {e}")

    return user_sessions


# ── 画像更新（v2.0）───────────────────────────────

def merge_sequence_into_profile(profile: dict, analysis: dict):
    """
    将本次分析的序列数据合并到画像的sequence字段中。
    核心逻辑：
    1. 追加last_N_styles（保留最近MAX_ROLLING_STYLES条）
    2. 合并全局转移矩阵
    3. 合并hour_style_profile
    """
    seq = profile.setdefault("sequence", _empty_sequence())
    new_styles = [s["style"] for s in analysis.get("style_sequence", [])]

    if not new_styles:
        return

    # 1. 追加last_N_styles
    seq["last_N_styles"].extend(new_styles)
    if len(seq["last_N_styles"]) > MAX_ROLLING_STYLES:
        seq["last_N_styles"] = seq["last_N_styles"][-MAX_ROLLING_STYLES:]

    # 2. 合并转移矩阵
    new_matrix = analysis.get("style_transition", {})
    for from_s, transitions in new_matrix.items():
        for to_s, count in transitions.items():
            key = f"{from_s}→{to_s}"
            curr = seq["style_transition"].get(key, 0)
            seq["style_transition"][key] = curr + count

    # 3. 合并hour_style_profile
    new_hour = analysis.get("hour_profile", {})
    for h, styles in new_hour.items():
        if h not in seq["hour_style_profile"]:
            seq["hour_style_profile"][h] = {}
        for style, count in styles.items():
            curr = seq["hour_style_profile"][h].get(style, 0)
            seq["hour_style_profile"][h][style] = curr + count

    seq["last_update_session"] += 1


def merge_decay_into_profile(profile: dict, analysis: dict, scan_days: int):
    """合并时域衰减数据（按扫描天数决定写入哪个桶）。"""
    decay = profile.setdefault("decay", _empty_decay())
    style_counter = Counter()
    for s in analysis.get("style_sequence", []):
        style_counter[s["style"]] += 1

    if scan_days <= 7:
        decay["last_7d_style"] = dict(style_counter)
        decay["last_7d_topics"] = dict(analysis.get("topics", Counter()).most_common(20)) \
            if hasattr(analysis.get("topics", {}), "most_common") else {}
    if scan_days <= 30:
        decay["last_30d_style"] = dict(style_counter)


def update_profile(platform: str, user_id: str, session_messages: list,
                   scan_days: int = 7) -> dict:
    """分析一组消息，更新用户画像（v2.0含序列追踪）。"""
    profile = load_profile(platform, user_id)
    analysis = analyze_session_messages(session_messages)

    if analysis["msg_count"] == 0:
        return profile

    # 基础统计
    if profile["first_seen"] is None:
        profile["first_seen"] = time.time()
    profile["last_seen"] = time.time()
    profile["total_sessions"] += 1
    profile["total_messages"] += analysis["msg_count"]

    # v1.0 风格统计
    for style, count in analysis["style"].items():
        profile["style"][style] = profile["style"].get(style, 0) + count

    # 活跃时间
    for h in analysis["hours"]:
        profile["active_hours"][str(h)] = profile["active_hours"].get(str(h), 0) + 1
    for d in analysis["days"]:
        profile["active_days"][str(d)] = profile["active_days"].get(str(d), 0) + 1

    # 消息长度（P0-3修复：分位数截断 + 上限控制）
    raw_lens = analysis["msg_lengths"]
    # 截断超过2000字符的极端值
    raw_lens = [min(l, 2000) for l in raw_lens]
    profile["avg_msg_len"].extend(raw_lens)
    # 只保留最近500条原始值（防止无限膨胀）
    if len(profile["avg_msg_len"]) > 500:
        profile["avg_msg_len"] = profile["avg_msg_len"][-500:]

    # 话题（兼容旧版）
    _merge_topics(profile, analysis)

    # ── v2.0 序列追踪 ──
    merge_sequence_into_profile(profile, analysis)
    merge_decay_into_profile(profile, analysis, scan_days)

    # 偏好推断
    _update_preferences(profile)

    # 快照
    _record_snapshot(profile)

    save_profile(profile)
    return profile


def _merge_topics(profile: dict, analysis: dict):
    """兼容旧版topic格式的合并逻辑。"""
    if isinstance(profile["topics"], list):
        try:
            if profile["topics"] and isinstance(profile["topics"][0], (list, tuple)):
                profile["topics"] = dict(profile["topics"])
            else:
                profile["topics"] = dict(Counter(profile["topics"]))
        except (ValueError, TypeError):
            profile["topics"] = {}
    if not isinstance(profile["topics"], dict):
        profile["topics"] = {}
    for topic, count in analysis.get("topics", {}).items():
        profile["topics"][topic] = profile["topics"].get(topic, 0) + count
    top20 = Counter(profile["topics"]).most_common(20)
    profile["topics"] = dict(top20)


def _update_preferences(profile: dict):
    pref = profile["response_preferences"]
    msgs = profile["total_messages"]
    if msgs > 5:
        tech_ratio = profile["style"].get("technical", 0) / msgs
        pref["prefers_technical_depth"] = tech_ratio > 0.3
        casual_ratio = profile["style"].get("casual", 0) / msgs
        pref["prefers_conciseness"] = casual_ratio > 0.4


def _record_snapshot(profile: dict):
    if profile["total_sessions"] % 10 == 0:
        snapshot = {
            "at": time.time(),
            "total_messages": profile["total_messages"],
            "top_topics": list(profile["topics"].keys())[:5],
            "dominant_style": max(profile["style"], key=profile["style"].get),
        }
        profile["growth_history"].append(snapshot)


# ── 画像报告生成 ──────────────────────────────────

def generate_report(platform: str, user_id: str) -> str:
    """生成用户画像可读报告（v2.0含序列信息）。"""
    profile = load_profile(platform, user_id)
    if not profile.get("total_messages", 0):
        return f"用户 {user_id} 暂无数据。"

    hours = Counter({int(k): v for k, v in profile.get("active_hours", {}).items()})
    peak_hour = hours.most_common(1)[0][0] if hours else 12
    peak_label = ""
    for (lo, hi), label in TIME_BUCKETS.items():
        if lo <= peak_hour < hi:
            peak_label = label
            break

    dominant_style = max(profile["style"], key=profile["style"].get) if profile["style"] else "unknown"

    # v2.0 序列数据
    seq = profile.get("sequence", {})
    last_n = seq.get("last_N_styles", [])
    transition = seq.get("style_transition", {})
    top_transitions = sorted(transition.items(), key=lambda x: -x[1])[:5]

    topics = profile.get("topics", {})
    top_topics = list(dict(Counter(topics).most_common(10)).keys())

    lines = [
        f"## 👤 用户画像: {user_id[:20]}",
        f"━━━━━━━━━━━━━━━━━━",
        f"平台: {platform}",
        f"总会话: {profile['total_sessions']} | 总消息: {profile['total_messages']}",
        f"活跃高峰: {peak_label} ({peak_hour}:00)",
        f"语言风格: {dominant_style}",
        "",
        f"📝 Top话题:",
    ]
    for t in top_topics[:8]:
        lines.append(f"  • {t}")

    # v2.0: 序列报告
    lines.append("")
    lines.append(f"🔗 风格序列 (最近{len(last_n)}条):")
    if last_n:
        lines.append(f"  {' → '.join(last_n[-10:])}")
    if top_transitions:
        lines.append(f"🏭 主要风格转移:")
        for k, v in top_transitions:
            lines.append(f"  {k}: {v}次")

    # 预测摘要
    from profile_predictor import predict_next_style
    pred = predict_next_style(profile, datetime.now().hour)
    if pred and pred.get("confidence", 0) >= 0.5:
        lines.append("")
        lines.append(f"🎯 预测下一风格: {pred['predicted_style']} "
                     f"(置信度 {pred['confidence']:.0%})")
        lines.append(f"  推荐模式: {pred['recommended_depth']} / {pred['recommended_length']}")

    pref = profile.get("response_preferences", {})
    if pref.get("prefers_technical_depth") is True:
        lines.append(f"\n🧠 偏好深度技术回答")
    if pref.get("prefers_conciseness") is True:
        lines.append(f"📏 偏好简短回复")

    return "\n".join(lines)


# ── 批量更新 ──────────────────────────────────────

def batch_update(days: int = 7):
    """扫描最近会话，批量更新所有用户画像。"""
    print(f"📊 批量更新画像 v2.0 (扫描最近{days}天)")
    print(f"   会话DB: {SESSION_DB}")

    user_sessions = scan_recent_sessions(days)
    print(f"   发现 {len(user_sessions)} 个用户会话流")

    for user_key, messages in user_sessions.items():
        try:
            platform, user_id = user_key.split(":", 1)
            profile = update_profile(platform, user_id, messages, scan_days=days)
            print(f"   ✅ {platform}:{user_id[:20]} → {profile['total_messages']}条消息")

            # 预测验证
            try:
                from profile_predictor import predict_next_style
                pred = predict_next_style(profile, datetime.now().hour)
                if pred and pred.get("confidence", 0) >= 0.5:
                    print(f"      🎯 预测: {pred['predicted_style']} (置信度 {pred['confidence']:.0%})")
            except ImportError:
                pass
        except Exception as e:
            print(f"   ⚠️ {user_key[:30]} → 失败: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n   所有用户画像已保存至 {PROFILES_DIR}")
    return list_all_users()


def list_all_users() -> list[dict]:
    """列出所有已建立画像的用户。"""
    users = []
    for f in sorted(PROFILES_DIR.glob("*.json")):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
            users.append({
                "platform": p.get("platform", "?"),
                "user_id": p.get("user_id", "?"),
                "total_msgs": p.get("total_messages", 0),
                "last_seen": p.get("last_seen"),
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return users


# ── CLI入口 ───────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "update":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        batch_update(days)

    elif len(sys.argv) > 1 and sys.argv[1] == "list":
        users = list_all_users()
        print(f"📋 已建立画像的用户 ({len(users)}):")
        for u in users:
            last = datetime.fromtimestamp(u["last_seen"]).strftime("%m-%d %H:%M") if u.get("last_seen") else "?"
            print(f"  {u['platform']:10s} | {u['user_id'][:24]:24s} | {u['total_msgs']:4d}条 | {last}")

    elif len(sys.argv) > 1 and sys.argv[1] == "report":
        platform = sys.argv[2] if len(sys.argv) > 2 else "feishu"
        user_id = sys.argv[3] if len(sys.argv) > 3 else ""
        if user_id:
            print(generate_report(platform, user_id))
        else:
            print("用法: python user_profiler.py report <platform> <user_id>")

    elif len(sys.argv) > 1 and sys.argv[1] == "demo":
        """演示：对当前用户运行预测链。"""
        platform = sys.argv[2] if len(sys.argv) > 2 else "weixin"
        user_id = sys.argv[3] if len(sys.argv) > 3 else ""
        if not user_id:
            print("用法: python user_profiler.py demo <platform> <user_id>")
        else:
            profile = load_profile(platform, user_id)
            if not profile.get("total_messages", 0):
                print(f"用户 {user_id} 暂无数据。")
            else:
                from profile_predictor import predict_next_style
                pred = predict_next_style(profile, datetime.now().hour)
                print(f"\n🧠 马卡洛夫预测链 — {platform}:{user_id[:20]}")
                print(f"━━━━━━━━━━━━━━━━━━━━━━━━")
                if pred:
                    for k, v in pred.items():
                        print(f"  {k}: {v}")
                else:
                    print("  数据不足，无法预测。")

    else:
        print("用户画像系统 — User Profiler v2.0 (马卡洛夫预测链)")
        print()
        print("用法:")
        print("  python user_profiler.py update [天数]   扫描会话并更新画像")
        print("  python user_profiler.py list             列出所有用户")
        print("  python user_profiler.py report <平台> <ID>  生成用户报告")
        print("  python user_profiler.py demo <平台> <ID>   预测链演示")
        print()
        print(f"  画像存储: {PROFILES_DIR}")
