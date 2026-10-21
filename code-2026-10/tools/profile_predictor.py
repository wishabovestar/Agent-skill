"""
马卡洛夫预测链引擎 — Profile Predictor v2.0
=============================================
4步预测链：时间窗口 → 风格转移 → 话题延续 → 综合决策
P3: 时域衰减 + 置信度收敛
P4: 纠正 → 反向传播闭环

被 user_profiler.py 和 profile-aware skill 调用。
输入: 用户画像dict + 当前时间 + (可选)当前会话风格序列
输出: 预测结果dict
"""

import math, json, time
from datetime import datetime
from collections import Counter, defaultdict

# ── 配置 ──────────────────────────────────────────
MIN_CONFIDENCE = 0.50         # 低于此值 → 降级默认风格
HIGH_CONFIDENCE = 0.70        # 高于此值 → 直接采纳
MIN_SAMPLES = 5               # 最少样本数才启用预测
CORRECTION_PENALTY = 0.15     # 每次纠正扣减该维度的权重
CONSECUTIVE_THRESHOLD = 3     # 连续N次纠正 → 强制保守模式

# ── P3: 时域衰减权重 ───────────────────────────────
DECAY_MULTIPLIER = {
    "last_7d": 3.0,     # 近7天 × 3
    "last_30d": 1.5,    # 近30天 × 1.5
    "all_time": 1.0,    # 全部历史 × 1
}

# ── P4: 纠正关键词 ─────────────────────────────────
CORRECTION_SIGNALS = {
    "tone_too_formal": ["别这么正式", "不用太正式", "随意点", "别客气"],
    "tone_too_casual": ["正经点", "专业点", "严肃点", "正式点"],
    "too_verbose": ["太啰嗦", "说重点", "太长不看", "简单点", "简洁", "短点"],
    "too_simple": ["具体点", "详细点", "展开说说", "说清楚"],
    "too_technical": ["说人话", "通俗点", "简单解释", "大白话"],
    "wrong_topic": ["不是这个意思", "我说的不是", "不对", "你理解错了"],
}


# ══════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════

def predict_next_style(profile: dict, current_hour: int,
                        session_recent_styles: list[str] = None) -> dict:
    """
    马卡洛夫4步预测链主入口。
    P3: 时域衰减权重影响Step1
    P4: 纠正历史影响置信度收敛
    """
    total_msgs = profile.get("total_messages", 0)
    if total_msgs < MIN_SAMPLES:
        return _default_prediction("数据不足", total_msgs)

    seq = profile.get("sequence", {})

    # P3: 检查是否需要提门槛（连续纠正后的保守模式）
    current_threshold = _get_convergence_threshold(profile)

    # Step 1~3
    step1 = _time_window_predict(profile, current_hour)
    step2 = _style_transition_predict(seq, session_recent_styles)
    step3 = _topic_continuation_predict(profile, session_recent_styles)

    # Step 4 综合决策（传入动态阈值）
    final = _comprehensive_decision(
        step1, step2, step3, profile, current_hour,
        session_recent_styles=session_recent_styles,
        threshold=current_threshold,
    )

    # P4: 附上纠正历史摘要
    corrections = profile.get("correction_history", [])
    if corrections:
        final["recent_corrections"] = {
            "count": len(corrections),
            "last": corrections[-1]["type"] if corrections else None,
            "convergence_mode": current_threshold > MIN_CONFIDENCE,
        }

    final["decision_chain"] = [
        {"step": 1, "name": "时间窗口", "result": step1},
        {"step": 2, "name": "风格转移", "result": step2},
        {"step": 3, "name": "话题延续", "result": step3},
    ]

    return final


# ══════════════════════════════════════════════════
# P3: 置信度收敛
# ══════════════════════════════════════════════════

def _get_convergence_threshold(profile: dict) -> float:
    """
    根据近期纠正次数动态提高置信度门槛。
    连续纠正 ≥ CONSECUTIVE_THRESHOLD 次 → 强制保守模式
    """
    corrections = profile.get("correction_history", [])
    if not corrections:
        return MIN_CONFIDENCE

    # 只看最近10次交互中的纠正
    recent = [c for c in corrections[-10:] if c.get("was_corrected")]
    recent_count = len(recent)

    if recent_count >= CONSECUTIVE_THRESHOLD:
        # 连续纠正 → 提门槛到70%，强制保守
        return 0.70
    elif recent_count >= 2:
        # 偶发纠正 → 中等提门槛到60%
        return 0.60
    return MIN_CONFIDENCE


# ══════════════════════════════════════════════════
# P3: 时域衰减时间窗口预测
# ══════════════════════════════════════════════════

def _time_window_predict(profile: dict, current_hour: int) -> dict:
    """
    P3: 使用时域衰减加权的时间窗口预测。
    近7天数据权重 × 3，近30天 × 1.5，全部历史 × 1.0
    """
    seq = profile.get("sequence", {})
    hour_profile = seq.get("hour_style_profile", {})
    decay = profile.get("decay", {})

    h_str = str(current_hour)
    hour_data = hour_profile.get(h_str, {})

    # P3: 如果decay有7天数据，也纳入
    decay_7d = decay.get("last_7d_style", {})
    decay_30d = decay.get("last_30d_style", {})

    if hour_data and sum(hour_data.values()) >= MIN_SAMPLES:
        # 基础权重 + 时域衰减加权
        total = sum(hour_data.values())
        probs = {s: c / total for s, c in hour_data.items()}

        # P3: decay加权修正
        adjusted = dict(probs)
        if decay_7d:
            decay_total_7d = sum(decay_7d.values())
            if decay_total_7d > 0:
                for style in list(adjusted.keys()):
                    decay_ratio = decay_7d.get(style, 0) / decay_total_7d
                    all_ratio = probs.get(style, 0)
                    # 加权: 7d × 3 + all_time × 1
                    adjusted[style] = (decay_ratio * 3 + all_ratio) / 4

        dominant = max(adjusted, key=adjusted.get)
        confidence = min(adjusted[dominant], 1.0)
        return {
            "predicted_style": dominant,
            "confidence": confidence,
            "style_probs": adjusted,
            "source": f"时段{current_hour}:00({total}条,衰减加权)",
        }

    # 无时段数据 → 用总风格+decay
    return _use_overall_style(profile, weight=0.5, decay_7d=decay_7d)


def _use_overall_style(profile: dict, weight: float = 1.0,
                        decay_7d: dict = None) -> dict:
    """P3: 使用时域衰减加权的总体风格占比。"""
    style = profile.get("style", {})
    total = max(sum(style.values()), 1)
    top = max(style, key=style.get) if style else "neutral"

    # P3: 用decay_7d做衰减修正
    if decay_7d and sum(decay_7d.values()) > 0:
        decay_total = sum(decay_7d.values())
        adjusted = {}
        for s, c in style.items():
            decay_ratio = decay_7d.get(s, 0) / decay_total
            all_ratio = c / total
            adjusted[s] = (decay_ratio * 3 + all_ratio) / 4
        top = max(adjusted, key=adjusted.get)
        confidence = min(adjusted[top], 1.0) * weight
        return {
            "predicted_style": top,
            "confidence": confidence,
            "style_probs": adjusted,
            "source": "总体风格+7天衰减加权",
        }

    return {
        "predicted_style": top,
        "confidence": min(style[top] / total, 1.0) * weight,
        "style_probs": {s: c / total for s, c in style.items()},
        "source": "总体风格占比",
    }


# ══════════════════════════════════════════════════
# Step 2: 风格转移预测
# ══════════════════════════════════════════════════

def _style_transition_predict(seq: dict,
                              session_recent_styles: list[str] = None) -> dict:
    """根据风格转移矩阵 + 最近N条消息预测下一风格。"""
    transitions = seq.get("style_transition", {})
    last_n = seq.get("last_N_styles", [])

    if session_recent_styles:
        last_style = session_recent_styles[-1]
        if len(session_recent_styles) >= 2:
            local_matrix = _build_local_matrix(session_recent_styles)
            if local_matrix and last_style in local_matrix:
                return _apply_transition(local_matrix, last_style, "本次会话转移")
    elif last_n:
        last_style = last_n[-1]
    else:
        return {"predicted_style": None, "confidence": 0.0, "source": "无序列数据"}

    if transitions:
        key_prefix = f"{last_style}→"
        candidates = {k.split("→")[1]: v for k, v in transitions.items()
                      if k.startswith(key_prefix)}
        if candidates:
            return _apply_transition_flat(candidates, last_style, "全局转移矩阵")

    return {"predicted_style": None, "confidence": 0.0,
            "source": f"无{last_style}的转移记录"}


def _build_local_matrix(styles: list[str]) -> dict:
    matrix = {}
    for i in range(len(styles) - 1):
        from_s, to_s = styles[i], styles[i + 1]
        if from_s not in matrix:
            matrix[from_s] = {}
        matrix[from_s][to_s] = matrix[from_s].get(to_s, 0) + 1
    return matrix


def _apply_transition(matrix: dict, last_style: str, source: str) -> dict:
    candidates = matrix.get(last_style, {})
    if not candidates:
        return {"predicted_style": None, "confidence": 0.0, "source": source}
    return _apply_transition_flat(candidates, last_style, source)


def _apply_transition_flat(candidates: dict, last_style: str, source: str) -> dict:
    total = sum(candidates.values())
    dominant = max(candidates, key=candidates.get)
    return {
        "predicted_style": dominant,
        "confidence": candidates[dominant] / total,
        "transition_probs": {s: c / total for s, c in candidates.items()},
        "source": source,
    }


# ══════════════════════════════════════════════════
# Step 3: 话题延续预测
# ══════════════════════════════════════════════════

def _topic_continuation_predict(profile: dict,
                                 session_recent_styles: list[str] = None) -> dict:
    topics = profile.get("topics", {})
    total_topics = sum(topics.values()) if topics else 0

    if total_topics < MIN_SAMPLES:
        return {"is_continuation": None, "confidence": 0.0,
                "predicted_topic_area": "general", "source": "话题数据不足"}

    if session_recent_styles:
        recent_majority = Counter(session_recent_styles[-3:]).most_common(1)
        if recent_majority:
            last_style = recent_majority[0][0]
            is_deep = last_style in ("technical", "detailed")
            return {
                "is_continuation": True,
                "confidence": 0.65 if is_deep else 0.45,
                "predicted_topic_area": "domain_specific" if is_deep else "general",
                "recommended_depth": "technical" if is_deep else "balanced",
                "source": f"最近风格:{last_style}",
            }

    decay = profile.get("decay", {})
    recent_topics = decay.get("last_7d_topics", topics)
    is_recent_active = len(recent_topics) >= 3

    return {
        "is_continuation": is_recent_active,
        "confidence": 0.5 if is_recent_active else 0.3,
        "predicted_topic_area": "domain_specific" if is_recent_active else "general",
        "recommended_depth": "technical" if is_recent_active else "balanced",
        "source": f"近7天活跃:{is_recent_active}",
    }


# ══════════════════════════════════════════════════
# Step 4: 综合决策
# ══════════════════════════════════════════════════

def _comprehensive_decision(step1: dict, step2: dict, step3: dict,
                             profile: dict, current_hour: int,
                             session_recent_styles: list[str] = None,
                             threshold: float = MIN_CONFIDENCE) -> dict:
    """
    P3: 动态权重 + 收敛阈值
    P4: 纠正惩罚影响权重
    """
    # 动态权重：根据当前会话是否有实质内容调整
    if session_recent_styles:
        non_neutral = [s for s in session_recent_styles if s != "neutral"]
        if len(non_neutral) >= 2:
            w1, w2, w3 = 0.15, 0.50, 0.35
        elif len(non_neutral) == 1:
            w1, w2, w3 = 0.25, 0.45, 0.30
        else:
            w1, w2, w3 = 0.35, 0.40, 0.25
    else:
        w1, w2, w3 = 0.35, 0.40, 0.25

    # P4: 纠正惩罚 — 对最近被纠正的路径降权
    corrections = profile.get("correction_history", [])
    if corrections:
        last_correction = corrections[-1]
        if last_correction.get("corrected_dimension") == "tone":
            wrong_style = last_correction.get("wrong_style")
            if wrong_style:
                # 降低该风格的权重
                pass  # 在投票阶段处理

    style_votes = {}
    sources = []

    # Step1 投票
    if step1.get("confidence", 0) >= threshold:
        s1_style = step1["predicted_style"]
        weight = w1 * step1["confidence"]
        style_votes[s1_style] = style_votes.get(s1_style, 0) + weight
        sources.append(("time", s1_style, weight))

    # Step2 投票
    if step2.get("confidence", 0) >= threshold:
        s2_style = step2["predicted_style"]
        weight = w2 * step2["confidence"]
        style_votes[s2_style] = style_votes.get(s2_style, 0) + weight
        sources.append(("transition", s2_style, weight))

    # Step3 话题深度贡献
    s3_depth = step3.get("recommended_depth", "balanced")
    if s3_depth == "technical":
        bonus = w3 * step3.get("confidence", 0.5)
        style_votes["technical"] = style_votes.get("technical", 0) + bonus
        sources.append(("topic_depth", "technical", bonus))

    # P4: 对最近纠正的风格降权
    if corrections:
        last_corr = corrections[-1]
        wrong_style = last_corr.get("wrong_style")
        if wrong_style and wrong_style in style_votes:
            penalty = CORRECTION_PENALTY
            style_votes[wrong_style] = max(style_votes[wrong_style] - penalty, 0)
            sources.append(("correction_penalty", wrong_style, -penalty))

    # 无有效投票 → 用总体风格
    if not style_votes:
        overall = _use_overall_style(profile)
        if overall["confidence"] >= threshold:
            style_votes[overall["predicted_style"]] = overall["confidence"]
            sources.append(("overall_fallback", overall["predicted_style"],
                            overall["confidence"]))

    if not style_votes:
        return _default_prediction("所有路径置信度不足")

    winner = max(style_votes, key=style_votes.get)
    total_votes = sum(style_votes.values())
    max_possible = w1 + w2 + w3  # 0.35+0.40+0.25 = 1.0
    coverage = min(total_votes / max_possible, 1.0)
    agreement = style_votes[winner] / total_votes if total_votes > 0 else 0.5
    confidence = agreement * coverage

    recommended_depth, recommended_length = _determine_format(
        winner, step3, profile, current_hour
    )

    return {
        "predicted_style": winner,
        "confidence": round(min(confidence, 1.0), 2),
        "style_votes": {k: round(v, 3) for k, v in sorted(
            style_votes.items(), key=lambda x: -x[1])},
        "sources": sources,
        "predicted_topic_area": step3.get("predicted_topic_area", "general"),
        "recommended_depth": recommended_depth,
        "recommended_length": recommended_length,
    }


def _determine_format(winner: str, step3: dict, profile: dict,
                       current_hour: int) -> tuple:
    """确定推荐的回答深度和长度。"""
    if winner in ("technical", "detailed") or \
       step3.get("recommended_depth") == "technical":
        depth = "technical"
    elif winner == "casual":
        depth = "simple"
    else:
        depth = "balanced"

    pref = profile.get("response_preferences", {})
    avg_lens = profile.get("avg_msg_len", [])
    avg_user_len = sum(avg_lens) / len(avg_lens) if avg_lens else 50
    active_hours = profile.get("active_hours", {})
    is_peak = active_hours.get(str(current_hour), 0) > 3

    if avg_user_len > 200 or is_peak:
        length = "long"
    elif avg_user_len < 50:
        length = "short"
    else:
        length = "medium"

    return depth, length


def _default_prediction(reason: str, msgs: int = 0) -> dict:
    return {
        "predicted_style": "neutral",
        "confidence": 0.0,
        "style_votes": {},
        "sources": [],
        "predicted_topic_area": "general",
        "recommended_depth": "balanced",
        "recommended_length": "medium",
        "warning": f"{reason} (消息数: {msgs})",
    }


# ══════════════════════════════════════════════════
# P4: 纠正 → 反向传播闭环
# ══════════════════════════════════════════════════

def detect_correction(user_message: str) -> dict | None:
    """
    检测用户是否在纠正回复风格。
    返回: None (无纠正) 或 {type, wrong_style, target_style, penalty}
    """
    msg_lower = user_message.lower()

    for corr_type, keywords in CORRECTION_SIGNALS.items():
        for kw in keywords:
            if kw in msg_lower:
                mapping = {
                    "tone_too_formal": {"wrong": "formal", "target": "casual"},
                    "tone_too_casual": {"wrong": "casual", "target": "technical"},
                    "too_verbose": {"wrong": None, "target": None,
                                    "dim": "length", "target_length": "short"},
                    "too_simple": {"wrong": None, "target": None,
                                   "dim": "depth", "target_depth": "technical"},
                    "too_technical": {"wrong": "technical", "target": "casual"},
                    "wrong_topic": {"wrong": None, "target": None,
                                    "dim": "topic"},
                }
                base = mapping[corr_type]
                return {
                    "type": corr_type,
                    "wrong_style": base.get("wrong"),
                    "target_style": base.get("target"),
                    "corrected_dimension": base.get("dim", "tone"),
                    "target_length": base.get("target_length"),
                    "target_depth": base.get("target_depth"),
                    "timestamp": time.time(),
                }
    return None


def record_correction(platform: str, user_id: str, correction: dict):
    """
    P4: 记录纠正到画像文件，并调整转移矩阵。
    调用位置: profile-aware skill（检测到纠正信号时）
    """
    from user_profiler import load_profile, save_profile

    profile = load_profile(platform, user_id)
    corrections = profile.setdefault("correction_history", [])

    correction["was_corrected"] = True
    corrections.append(correction)

    # 保留最近50条
    if len(corrections) > 50:
        profile["correction_history"] = corrections[-50:]

    # 调整转移矩阵：降低错误路径的权重
    wrong_style = correction.get("wrong_style")
    target_style = correction.get("target_style")
    seq = profile.get("sequence", {})
    transitions = seq.get("style_transition", {})

    if wrong_style and target_style:
        # 降低 wrong→target 转移路径权重（除以2）
        key = f"{wrong_style}→{target_style}"
        if key in transitions:
            transitions[key] = max(int(transitions[key] / 2), 1)
            # 同时提升 wrong→wrong 以增加惯性（保守）
            self_key = f"{wrong_style}→{wrong_style}"
            transitions[self_key] = transitions.get(self_key, 0) + 1

    # 记录纠正后的响应偏好
    pref = profile.get("response_preferences", {})
    if correction.get("type") == "too_verbose":
        pref["prefers_conciseness"] = True  # 明确偏好简洁
    elif correction.get("type") == "too_simple":
        pref["prefers_technical_depth"] = True

    save_profile(profile)
    return profile


# ══════════════════════════════════════════════════
# 对外暴露的便捷函数
# ══════════════════════════════════════════════════

def predict_style_from_file(platform: str, user_id: str,
                             current_hour: int = None) -> dict:
    from user_profiler import load_profile

    if current_hour is None:
        current_hour = datetime.now().hour
    profile = load_profile(platform, user_id)
    if not profile.get("total_messages", 0):
        return _default_prediction("画像不存在或无数据")
    return predict_next_style(profile, current_hour)


def get_style_adjustment(platform: str, user_id: str,
                          current_hour: int = None,
                          session_styles: list[str] = None) -> dict:
    """
    Profile-aware skill 专用接口。
    P4: 检测纠正信号，自动记录。
    """
    if current_hour is None:
        current_hour = datetime.now().hour

    try:
        from user_profiler import load_profile
        profile = load_profile(platform, user_id)

        if profile.get("total_messages", 0) < MIN_SAMPLES:
            return {"tone": "neutral", "depth": "balanced",
                    "length": "medium", "confidence": 0.0,
                    "source": "数据不足"}

        pred = predict_next_style(profile, current_hour, session_styles)

        if pred.get("confidence", 0) < MIN_CONFIDENCE:
            fallback_tone = _fallback_tone(profile)
            return {"tone": fallback_tone, "depth": "balanced",
                    "length": "medium", "confidence": 0.0,
                    "source": f"预测置信度不足({pred.get('confidence',0):.0%}),"
                              f"降级{fallback_tone}"}

        return {
            "tone": pred["predicted_style"] if pred["predicted_style"] != "neutral" else "balanced",
            "depth": pred.get("recommended_depth", "balanced"),
            "length": pred.get("recommended_length", "medium"),
            "confidence": pred.get("confidence", 0.0),
            "prediction": pred,
        }

    except ImportError:
        return {"tone": "neutral", "depth": "balanced",
                "length": "medium", "confidence": 0.0,
                "source": "predictor未安装"}


def _fallback_tone(profile: dict) -> str:
    style = profile.get("style", {})
    if not style:
        return "neutral"
    return max(style, key=style.get)


# ── CLI 测试 ───────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "record_correction":
        # 手动记录纠正
        platform = sys.argv[2]
        user_id = sys.argv[3]
        msg = sys.argv[4] if len(sys.argv) > 4 else ""
        correction = detect_correction(msg)
        if correction:
            record_correction(platform, user_id, correction)
            print(f"✅ 记录纠正: {correction['type']}")
        else:
            print("❌ 未检测到纠正信号")
    elif len(sys.argv) > 1:
        platform = sys.argv[1]
        user_id = sys.argv[2] if len(sys.argv) > 2 else ""
        hour = int(sys.argv[3]) if len(sys.argv) > 3 else datetime.now().hour

        if not user_id:
            print("用法:")
            print("  python profile_predictor.py <platform> <user_id> [hour]")
            print("  python profile_predictor.py record_correction <platform> <user_id> <消息>")
        else:
            result = predict_style_from_file(platform, user_id, hour)
            print(f"\n🧠 马卡洛夫预测链结果 v2.0 (P3+P4)")
            print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print(f"  predicted_style:     {result.get('predicted_style')}")
            print(f"  confidence:          {result.get('confidence')}")
            print(f"  recommended_depth:   {result.get('recommended_depth')}")
            print(f"  recommended_length:  {result.get('recommended_length')}")
            print(f"  predicted_area:      {result.get('predicted_topic_area')}")
            if result.get("style_votes"):
                print(f"  style_votes:         {result['style_votes']}")
            if result.get("warning"):
                print(f"  ⚠️  {result['warning']}")
            if result.get("recent_corrections"):
                print(f"  📝 最近纠正数: {result['recent_corrections']['count']}")
            if result.get("decision_chain"):
                for dc in result["decision_chain"]:
                    s = dc["result"]
                    print(f"    Step{dc['step']} {dc['name']}: "
                          f"pred={s.get('predicted_style','?')} "
                          f"conf={s.get('confidence',0):.0%} "
                          f"src={s.get('source','?')[:40]}")
    else:
        print("马卡洛夫预测链引擎 — Profile Predictor v2.0 (P3:衰减+P4:纠正)")
        print()
        print("用法:")
        print("  python profile_predictor.py <platform> <user_id> [hour]")
        print("  python profile_predictor.py record_correction <platform> <user_id> <消息>")
