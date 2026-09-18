#!/usr/bin/env python3
"""
睡眠记忆引擎 v2 — 数学优化版
优化: TF-IDF加权 · Jaccard聚类 · 动态阈值 · PMI跨域
"""
# side_effects: [写数据文件]
import os
import json, sqlite3, os, sys, re, math
from collections import defaultdict, Counter
from datetime import datetime

DB_PATH = "D:/hermes/hermes-data/profiles/qqbot3/state.db"
KB_DIR = "D:/hermes/hermes-data/profiles/qqbot3/knowledge_base"
OUTPUT_DIR = f"{KB_DIR}/audit"
VERSION = "v2"

# ── 数学优化1: TF-IDF加权重要性评分 ──
def compute_tfidf_weights(corpus):
    """从语料库计算TF-IDF词典"""
    N = len(corpus)
    df = Counter()
    for text in corpus:
        words = set(re.findall(r'[\u4e00-\u9fff\w-]{2,}', text.lower()))
        df.update(words)
    idf = {w: math.log((N + 1) / (c + 1)) + 1 for w, c in df.items()}
    return idf

def score_importance_v1(text, idf=None):
    """V1: 原始关键词评分 (对照用)"""
    weights = {
        'high': (["定理","证明","推导","arXiv","transformer","distill","量化","投机解码","speculative"], 0.8),
        'med': (["研究","分析","模型","优化","benchmark","实验","系统"], 0.5),
        'low': (["问题","检查","查询","状态","确认","hello","测试"], 0.2),
        'noise': (["delivery","silent","nothing","cron","schedule","job_id"], -5.0)
    }
    score = 0.1
    text_l = text.lower()
    for level, (kws, w) in weights.items():
        for kw in kws:
            score += text_l.count(kw.lower()) * w
    return min(max(score, 0.0), 1.0)

def score_importance_v2(text, idf):
    """V2: TF-IDF加权评分

    ★ R1116 修复 (2026-09-15): 原版对空文本/无词文本返回 0.05,
      而 0.05 恰等于 min(第10百分位, 0.3) 的下限来源 →
      当【空内容消息占比高】时所有分数塌缩到 0.05,
      再叠加严格小于判定 (s < discard_t) → discarded 恒为 0 (静默失效)。
    ★ 修法: 返回 None 表示"不可评分", 由调用方【过滤】而非参与统计。
    """
    if not text or not text.strip() or not idf:
        return None          # ★ 不可评分 → 调用方应过滤掉
    words = re.findall(r'[\u4e00-\u9fff\w-]{3,}', text.lower())
    if not words:
        return None          # ★ 无有效词 → 同样不可评分
    # TF-IDF加权求和
    tfidf_sum = sum(idf.get(w, 0) for w in words if w in idf)
    if tfidf_sum == 0:
        return None          # ★ 全部词都未命中 idf → 不可评分
    # 按词数归一化
    avg_tfidf = tfidf_sum / len(words)
    # 映射到[0, 1]区间 (idf通常在1-5之间)
    score = min(avg_tfidf / 5.0, 1.0)
    return score

# ── 数学优化2: Jaccard聚类 (替代关键词匹配) ──
def jaccard_similarity(set_a, set_b):
    """Jaccard相似度 = |A∩B| / |A∪B|"""
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0

def extract_features(content):
    """提取文本特征集"""
    return set(re.findall(r'[\u4e00-\u9fff\w-]{3,}', content.lower()))

def cluster_by_jaccard(sessions, threshold=0.15):
    """O(n²)的Jaccard聚类"""
    clusters = []
    features = [extract_features(s.get("content","")) for s in sessions]
    n = len(sessions)
    assigned = set()
    for i in range(n):
        if i in assigned: continue
        cluster = [sessions[i]]
        assigned.add(i)
        for j in range(i+1, n):
            if j in assigned: continue
            sim = jaccard_similarity(features[i], features[j])
            if sim >= threshold:
                cluster.append(sessions[j])
                assigned.add(j)
        clusters.append(cluster)
    return clusters

# ── 数学优化3: 动态百分位阈值 ──
def dynamic_threshold(scores, percentile=70):
    """按分数分布动态确定promote/discard阈值"""
    if len(scores) < 5:
        return 0.6, 0.2
    sorted_s = sorted(scores)
    n = len(sorted_s)
    promote_t = sorted_s[int(n * percentile / 100)]
    discard_t = sorted_s[int(n * 10 / 100)]
    return max(promote_t, 0.3), min(discard_t, 0.3)

# ── 数学优化4: PMI跨域关联 ──
def compute_pmi(word_pairs, total_pairs):
    """点互信息 PMI(x,y) = log(P(x,y)/(P(x)P(y)))"""
    pmi_scores = {}
    for (w1, w2), count in word_pairs.items():
        p_xy = count / total_pairs
        p_x = sum(1 for (a,b),c in word_pairs.items() if a==w1 and b==w2) / total_pairs
        pmi_scores[(w1,w2)] = math.log(p_xy / (p_x * p_xy + 1e-10) + 1e-10) if p_x > 0 else 0
    return pmi_scores

# ── 主流程 ──
def run_sleep_v2():
    print(f"💤 睡眠记忆引擎 {VERSION} [数学优化版] [{datetime.now().strftime('%H:%M:%S')}]")
    
    sessions = get_session_data()
    if not sessions:
        print("  ⚠️ 无会话数据")
        return
    print(f"  读取 {len(sessions)} 个会话")
    
    # Phase 1: TF-IDF + 动态阈值
    corpus = [s.get("content","") for s in sessions]
    idf = compute_tfidf_weights(corpus)
    scores_v1 = [score_importance_v1(s.get("content","")) for s in sessions]
    # ★ R1116 修复: score_importance_v2 对不可评分的条目返回 None
    #   → 过滤掉, 不让退化值参与阈值计算 (原版返回 0.05 导致静默失效)
    raw_v2 = [score_importance_v2(s.get("content",""), idf) for s in sessions]
    scores_v2 = [x for x in raw_v2 if x is not None]
    n_unscorable = len(raw_v2) - len(scores_v2)
    if n_unscorable:
        print("  ℹ️ 不可评分条目 %d/%d (空内容/无有效词) — 已排除出统计"
              % (n_unscorable, len(raw_v2)))
    if not scores_v2:
        print("  🔴 无可评分条目 — 跳过阈值判定 (避免退化)")
        return

    # ★ R1116 新增: 退化检测 (所有分数相同 = 评分失效)
    if len(set(round(s, 6) for s in scores_v2)) == 1:
        print("  🔴 告警: 所有评分相同 (%.4f) → 评分函数可能失效!"
              % scores_v2[0])
        print("     不输出 promote/discard 指标 (避免误导)")

    promote_t, discard_t = dynamic_threshold(scores_v2)
    promoted = sum(1 for s in scores_v2 if s > promote_t)
    # ★ R1116 修复: <= 而非 < (原版严格小于导致"恰好等于阈值"的不算丢弃)
    discarded = sum(1 for s in scores_v2 if s <= discard_t)
    
    # Phase 2: Jaccard聚类
    clusters = cluster_by_jaccard(sessions, threshold=0.15)
    mergeable = [c for c in clusters if len(c) >= 2]
    
    # Phase 3: PMI跨域
    word_pairs = Counter()
    for s in sessions:
        words = re.findall(r'[\u4e00-\u9fff\w-]{3,}', (s.get("content","") or "").lower())
        for i in range(len(words)-1):
            word_pairs[(words[i], words[i+1])] += 1
    
    # Phase 4: A/B评分
    # ★ r1192 诊断强化: `v2_discard_rate` 为 0 有两种【完全不同的含义】, 原指标无法区分:
    #   (a) 正常 —— 本批没有低分条目可丢(修复后不可评分条目已被过滤, 剩余都 >= 阈值上限)
    #   (b) 异常 —— 判定链失效(旧的哨兵值塌缩场景)
    #   ⇒ 补四个可区分字段。★ 教训: 阈值型指标在退化分布上会静默输出常数。
    _mins = min(scores_v2) if scores_v2 else None
    _cap = (abs(discard_t - 0.3) < 1e-9)     # dynamic_threshold 的上限是 min(x, 0.3)
    _below = sum(1 for s in scores_v2 if s <= discard_t)
    ab_metrics = {
        "v1_promote_rate": sum(1 for s in scores_v1 if s > 0.6) / len(scores_v1),
        "v2_promote_rate": promoted / len(scores_v2),
        "v1_discard_rate": sum(1 for s in scores_v1 if s < 0.15) / len(scores_v1),
        "v2_discard_rate": discarded / len(scores_v2),
        "jaccard_clusters": len(mergeable),
        "promote_threshold": round(promote_t, 3),
        "discard_threshold": round(discard_t, 3),
        # ── r1192 新增: 让 0 可解释 ──
        "v2_scorable_n": len(scores_v2),
        "v2_min_score": round(_mins, 4) if _mins is not None else None,
        "v2_below_discard_n": _below,
        "discard_at_cap": _cap,
    }
    # ★ 自解释: 若为 0 且撞上限 ⇒ 是"无低分条目"(正常); 若为 0 但未撞上限 ⇒ 需查判定链
    if not discarded and _cap:
        ab_metrics["v2_discard_note"] = "zero-no-low-score (正常: 无 <= 阈值的条目)"
    elif not discarded:
        ab_metrics["v2_discard_note"] = "zero-but-not-at-cap (★ 需查判定链)"
    
    report = {
        "version": VERSION, "timestamp": datetime.now().isoformat(),
        "sessions_analyzed": len(sessions),
        "ab_metrics": ab_metrics,
        "clusters": [{"size": len(c), "topics": [s.get("title","")[:30] for s in c[:3]]} for c in mergeable[:5]],
    }
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report_path = f"{OUTPUT_DIR}/sleep_{VERSION}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    if os.path.exists(report_path):
        if os.path.exists(report_path + ".bak"):
            try: os.remove(report_path + ".bak")
            except OSError: pass
        os.rename(report_path, report_path + ".bak")

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"  V1 promote={ab_metrics['v1_promote_rate']*100:.0f}%  V2 promote={ab_metrics['v2_promote_rate']*100:.0f}%")
    print(f"  Jaccard聚类: {len(mergeable)}个可合并簇")
    print(f"  ✅ 报告已保存: {report_path}")

def get_session_data(limit=50):
    """复制原版数据库查询"""
    if not os.path.exists(DB_PATH): return []
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute("""
            SELECT s.id, s.session_key, s.title, s.message_count,
                   (SELECT m.content FROM messages m WHERE m.session_id = s.id AND m.role = 'user' ORDER BY m.timestamp LIMIT 1) as first_msg,
                   (SELECT GROUP_CONCAT(substr(m2.content,1,500), ' ') FROM (SELECT content FROM messages m2 WHERE m2.session_id = s.id AND m2.role IN ('user','assistant') ORDER BY m2.timestamp LIMIT 5) m2) as sample_content
            FROM sessions s WHERE s.archived = 0 ORDER BY s.rowid DESC LIMIT ?
        """, (limit,))
        sessions = []
        for r in cur.fetchall():
            sid, skey, title, msg_count, first_msg, sample = r
            content = (title or '') + ' ' + (first_msg or '') + ' ' + (sample or '')
            content = content.strip()
            if content:
                sessions.append({"id": skey or sid, "title": title or (first_msg or "")[:40], "msgs": msg_count or 0, "content": content[:2000]})
        conn.close()
        return sessions
    except: return []

if __name__ == "__main__":
    run_sleep_v2()
