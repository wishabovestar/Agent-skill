"""
P4: 本地知识图谱 — 离线向量存储 (轻量版)
=========================================
零外部依赖: SQLite FTS5 + JSON + Python stdlib

核心设计:
  - 知识块 (knowledge_chunk): 来源 + 摘要 + 关键词 + 原始内容
  - FTS5 全文索引: 关键词搜索
  - TF 评分: 关键词出现频率排序
  - 自动过期: 旧知识逐渐降权

目标: 即使完全断网，也能从本地知识库回答常见问题。
"""

import sqlite3, json, time, re, hashlib
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

# ── 配置 ──
KNOWLEDGE_DB = Path("D:/hermes/analysis/knowledge_store.db")
DEFAULT_TTL_DAYS = 90       # 知识默认90天过期
DECAY_FACTOR = 0.9          # 每周衰减系数


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(KNOWLEDGE_DB))
    # FTS5 全文索引
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
            title, content, keywords, source,
            tokenize='unicode61'
        )
    """)
    # 元数据表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_meta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            content_hash TEXT UNIQUE,
            source TEXT,
            url TEXT,
            category TEXT,
            keywords TEXT,
            confidence REAL DEFAULT 0.7,
            created_at REAL,
            accessed_at REAL,
            access_count INTEGER DEFAULT 0,
            ttl_days INTEGER DEFAULT 90
        )
    """)
    conn.commit()
    return conn


# ── 知识写入 ──

def store_knowledge(title: str, content: str, source: str = "",
                     url: str = "", category: str = "general",
                     keywords: list[str] = None) -> dict:
    """
    存储一条知识到本地知识图谱。
    自动提取关键词、计算哈希、写入FTS索引。
    """
    if not content or len(content) < 50:
        return {"success": False, "error": "内容太短"}

    # 自动提取关键词
    if keywords is None:
        keywords = _extract_keywords(title + " " + content[:500])

    # 去重哈希
    content_hash = hashlib.md5(content.encode()).hexdigest()

    conn = _get_conn()
    cursor = conn.cursor()

    try:
        # 检查是否已存在
        existing = cursor.execute(
            "SELECT id FROM knowledge_meta WHERE content_hash = ?",
            (content_hash,)
        ).fetchone()

        if existing:
            # 更新访问时间和计数
            cursor.execute(
                "UPDATE knowledge_meta SET accessed_at = ?, access_count = access_count + 1 WHERE id = ?",
                (time.time(), existing[0])
            )
            conn.commit()
            return {"success": True, "duplicate": True, "id": existing[0]}

        # 写入元数据
        cursor.execute("""
            INSERT INTO knowledge_meta
            (title, content_hash, source, url, category, keywords, created_at, accessed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            title[:200], content_hash, source[:100], url[:500],
            category, json.dumps(keywords, ensure_ascii=False),
            time.time(), time.time()
        ))
        knowledge_id = cursor.lastrowid

        # 写入 FTS 索引
        keywords_str = " ".join(keywords)
        cursor.execute(
            "INSERT INTO knowledge_fts (rowid, title, content, keywords, source) VALUES (?, ?, ?, ?, ?)",
            (knowledge_id, title, content[:10000], keywords_str, source[:100])
        )

        conn.commit()
        return {"success": True, "id": knowledge_id,
                "keywords": keywords[:10],
                "title": title[:50]}

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def _extract_keywords(text: str, max_kw: int = 15) -> list[str]:
    """
    从文本中提取关键词。
    使用中文分词 + 英文单词拆分 + 频率排序。
    """
    # 中文2+字词
    cn_words = re.findall(r'[\u4e00-\u9fff]{2,}', text)
    # 英文单词 (>=3字母)
    en_words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())

    all_words = cn_words + en_words
    if not all_words:
        return ["general"]

    # 过滤停用词
    stopwords = {"this", "that", "with", "from", "have", "been", "were",
                 "will", "what", "when", "where", "which", "their", "there",
                 "about", "would", "could", "should", "after", "before",
                 "between", "other", "than", "also", "very", "just",
                 "以及", "但是", "而且", "因为", "所以", "虽然", "如果",
                 "可以", "没有", "这些", "那些", "这个", "那个", "一个",
                 "不是", "就是", "还是", "或者", "关于", "对于", "通过"}

    # 词频统计并过滤
    counter = Counter(w for w in all_words
                      if w.lower() not in stopwords and len(w) >= 2)

    # 返回top关键词
    return [w for w, _ in counter.most_common(max_kw)]


# ── 知识检索 ──

def search_knowledge(query: str, top_k: int = 5,
                      min_confidence: float = 0.3) -> list[dict]:
    """
    搜索本地知识库。
    使用 FTS5 全文搜索，TF 评分排序。
    """
    if not query.strip():
        return []

    conn = _get_conn()
    cursor = conn.cursor()

    # FTS5 搜索
    # 去掉标点符号，保留关键字符
    clean_query = re.sub(r'[^\w\u4e00-\u9fff\s]', ' ', query)
    clean_query = ' OR '.join(clean_query.split()[:10])

    try:
        cursor.execute("""
            SELECT
                kf.rowid,
                kf.title,
                kf.content,
                kf.keywords,
                kf.source,
                km.created_at,
                km.access_count,
                km.confidence,
                km.url,
                km.category
            FROM knowledge_fts kf
            JOIN knowledge_meta km ON kf.rowid = km.id
            WHERE knowledge_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (clean_query, top_k * 2))
    except:
        # 如果 FTS5 查询失败（查询词太短等），回退到 LIKE
        cursor.execute("""
            SELECT
                km.id, km.title, '', km.keywords, km.source,
                km.created_at, km.access_count, km.confidence, km.url, km.category
            FROM knowledge_meta km
            WHERE km.title LIKE ? OR km.keywords LIKE ?
            ORDER BY km.access_count DESC
            LIMIT ?
        """, (f'%{query}%', f'%{query}%', top_k * 2))

    results = []
    for row in cursor.fetchall():
        # 时域衰减
        age_days = (time.time() - row[5]) / 86400 if row[5] else 0
        weeks = age_days / 7
        decay = DECAY_FACTOR ** weeks
        confidence = (row[7] or 0.7) * decay

        if confidence < min_confidence:
            continue

        # 关键词匹配度评分
        kw_score = 0
        if row[3]:
            try:
                keywords = json.loads(row[3]) if isinstance(row[3], str) else row[3]
                query_terms = set(re.findall(r'[\w\u4e00-\u9fff]+', query.lower()))
                kw_match = sum(1 for kw in keywords if kw.lower() in query_terms)
                kw_score = kw_match / max(len(query_terms), 1)
            except:
                pass

        results.append({
            "id": row[0],
            "title": row[1],
            "content_preview": row[2][:200] if row[2] else "",
            "source": row[4],
            "url": row[8],
            "category": row[9],
            "confidence": round(confidence, 2),
            "keyword_match": round(kw_score, 2),
            "access_count": row[6],
            "age_days": round(age_days, 1),
        })

    conn.close()

    # 综合排序: confidence × 0.6 + keyword_match × 0.3 + access_bonus × 0.1
    for r in results:
        access_bonus = min(r["access_count"] / 10, 1.0)
        r["score"] = round(
            r["confidence"] * 0.6 +
            r["keyword_match"] * 0.3 +
            access_bonus * 0.1,
            3
        )

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


# ── 知识导出/导入 ──

def export_knowledge(path: str = None) -> str:
    """导出全部知识为 JSON"""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT title, source, url, category, keywords,
               created_at, access_count, confidence
        FROM knowledge_meta
        ORDER BY access_count DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    data = [{
        "title": r[0],
        "source": r[1],
        "url": r[2],
        "category": r[3],
        "keywords": json.loads(r[4]) if r[4] else [],
        "created_at": datetime.fromtimestamp(r[5]).isoformat() if r[5] else "",
        "access_count": r[6],
        "confidence": r[7],
    } for r in rows]

    output = json.dumps(data, ensure_ascii=False, indent=2)
    if path:
        Path(path).write_text(output, encoding="utf-8")
        return f"已导出 {len(data)} 条知识到 {path}"
    return output


# ── CLI ──

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "store":
        # 从 stdin 或参数读取
        title = sys.argv[2] if len(sys.argv) > 2 else "Untitled"
        content = sys.argv[3] if len(sys.argv) > 3 else ""
        source = sys.argv[4] if len(sys.argv) > 4 else "cli"
        result = store_knowledge(title, content, source=source)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif len(sys.argv) > 1 and sys.argv[1] == "search":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not query:
            print("用法: python knowledge_store.py search <查询>")
        else:
            results = search_knowledge(query)
            print(f"🔍 搜索: {query}")
            print(f"   结果: {len(results)}条")
            print()
            for r in results:
                kw = f"[KW:{r['keyword_match']}]" if r['keyword_match'] > 0 else ""
                print(f"   {r['title'][:60]}")
                print(f"   置信度: {r['confidence']:.0%} 访问: {r['access_count']}次 {kw}")
                print(f"   来源: {r['source']} | {r['url'][:60] if r['url'] else '-'}")
                print()

    elif len(sys.argv) > 1 and sys.argv[1] == "export":
        path = sys.argv[2] if len(sys.argv) > 2 else None
        print(export_knowledge(path))

    elif len(sys.argv) > 1 and sys.argv[1] == "stats":
        conn = _get_conn()
        count = conn.execute("SELECT COUNT(*) FROM knowledge_meta").fetchone()[0]
        accesses = conn.execute("SELECT SUM(access_count) FROM knowledge_meta").fetchone()[0] or 0
        categories = conn.execute(
            "SELECT category, COUNT(*) FROM knowledge_meta GROUP BY category"
        ).fetchall()
        conn.close()
        print(f"📊 知识图谱统计")
        print(f"  总知识条数: {count}")
        print(f"  总访问次数: {accesses}")
        print(f"  分类分布:")
        for cat, cnt in categories:
            print(f"    {cat}: {cnt}条")

    else:
        print("本地知识图谱 — Knowledge Store v1.0")
        print()
        print("用法:")
        print("  python knowledge_store.py store <title> <content> [source]")
        print("  python knowledge_store.py search <query>")
        print("  python knowledge_store.py export [file.json]")
        print("  python knowledge_store.py stats")
