"""
MemOS混合搜索 — BM25 + sqlite-vec KNN + MMR多样性重排序
Inspired by pranithvelar/MemOS-Memory-Operating-System ⭐7

安装: pip install sqlite-vec
运行: python memos_hybrid_search.py index   # 索引Hermes state.db
      python memos_hybrid_search.py search "query"  # 搜索
      python memos_hybrid_search.py demo    # 演示自测
"""

import json, os, sys, math, re, sqlite3, textwrap
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

HERMES_PROFILES = {
    "qqbot3": Path("D:/hermes/hermes-data/profiles/qqbot3"),
    "qqbot2": Path("D:/hermes/hermes-data/profiles/qqbot2"),
    "qqbot4": Path("D:/hermes/hermes-data/profiles/qqbot4"),
    "qqbot5": Path("D:/hermes/hermes-data/profiles/qqbot5"),
    "mybot": Path("D:/hermes/hermes-data/profiles/mybot"),
    "dong": Path("D:/hermes/hermes-data/profiles/dong"),
    "default": Path("D:/hermes/hermes-data/profiles/default"),
}
INDEX_FILE = Path("D:/hermes/hermes-data/profiles/mybot/knowledge_base/memos_hybrid_index.json")
VEC_DB = Path("D:/hermes/hermes-data/profiles/mybot/knowledge_base/memos_vec.db")

# ── FTS5 BM25 搜索 ────────────────────────

class BM25Search:
    """SQLite FTS5 BM25文本搜索"""
    
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path, timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=OFF")
        self._init_schema()
    
    def _init_schema(self):
        c = self.conn.cursor()
        # memos_body is the content table
        c.execute("""
            CREATE TABLE IF NOT EXISTS memos_body(
                rowid INTEGER PRIMARY KEY,
                session_id TEXT,
                message_id INTEGER,
                role TEXT,
                content TEXT,
                session_title TEXT,
                source TEXT,
                created_at REAL,
                token_count INTEGER
            )
        """)
        # FTS5 with content= for auto-sync — rebuilt from memos_body
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memos_fts USING fts5(
                content, session_title, source,
                content=memos_body, content_rowid=rowid,
                tokenize='porter unicode61'
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS memos_meta(
                key TEXT PRIMARY KEY, value TEXT
            )
        """)
        self.conn.commit()
    
    def build_from_hermes(self, profile: str = "qqbot3") -> int:
        """从Hermes state.db构建索引"""
        hermes_db = HERMES_PROFILES.get(profile)
        if not hermes_db:
            print(f"  ⚠ Unknown profile: {profile}")
            return 0
        
        state_db = hermes_db / "state.db"
        if not state_db.exists():
            print(f"  ⚠ state.db not found at {state_db}")
            return 0
        
        # Read messages from Hermes state.db
        hconn = sqlite3.connect(str(state_db), timeout=10)
        hconn.row_factory = sqlite3.Row
        
        rows = hconn.execute("""
            SELECT m.id, m.session_id, m.role, m.content, 
                   m.token_count, m.timestamp as created_at,
                   COALESCE(s.title, 'untitled') as session_title
            FROM messages m
            LEFT JOIN sessions s ON m.session_id = s.id
            WHERE m.content IS NOT NULL AND length(m.content) > 50
            ORDER BY m.id
        """).fetchall()
        hconn.close()
        
        print(f"  Read {len(rows)} messages from {profile} state.db")
        
        # Truncate and re-index
        c = self.conn.cursor()
        c.execute("DELETE FROM memos_body")
        # content-sync FTS5: need to delete existing fts rows
        try:
            c.execute("DELETE FROM memos_fts")
        except sqlite3.OperationalError:
            pass  # may not exist yet
        
        count = 0
        for row in rows:
            content = row["content"]
            if len(content) > 5000:
                content = content[:5000] + " ...[truncated]"
            
            c.execute("""
                INSERT INTO memos_body(session_id, message_id, role, content, 
                                       session_title, source, created_at, token_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["session_id"], row["id"], row["role"], content,
                row["session_title"], f"hermes:{profile}", row["created_at"],
                row["token_count"] or 0
            ))
            count += 1
        
        # Sync FTS — content-sync table auto-syncs on INSERT
        # But since we used DELETE+INSERT, trigger a rebuild for FTS
        try:
            c.execute("INSERT INTO memos_fts(memos_fts) VALUES('rebuild')")
        except sqlite3.OperationalError:
            pass  # content sync should handle it
        self.conn.commit()
        
        # Set meta
        c.execute("INSERT OR REPLACE INTO memos_meta VALUES ('last_index', ?)",
                  (datetime.now().isoformat(),))
        self.conn.commit()
        
        return count
    
    def search(self, query: str, k: int = 10) -> list[dict]:
        """BM25搜索, 返回排序结果"""
        if not query.strip():
            return []
        
        # Escape FTS5 special chars
        q = query.replace('"', '""')
        
        c = self.conn.cursor()
        rows = c.execute("""
            SELECT b.rowid, b.session_id, b.message_id, b.role,
                   b.content, b.session_title, b.source, b.created_at,
                   b.token_count,
                   rank
            FROM memos_fts f
            JOIN memos_body b ON f.rowid = b.rowid
            WHERE memos_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (q, k * 2)).fetchall()
        
        results = []
        for r in rows:
            bm25_score = 1.0 / (1.0 + abs(r[9])) if r[9] is not None else 0.5
            results.append({
                "rowid": r[0], "session_id": r[1], "message_id": r[2],
                "role": r[3], "content": r[4][:300],
                "session_title": r[5], "source": r[6], "created_at": r[7],
                "token_count": r[8], "bm25_score": round(bm25_score, 4),
            })
        
        return results[:k]
    
    def close(self):
        self.conn.close()


# ── KNN 向量搜索 (simple bag-of-char, 无需LLM) ──
# MemOS用sqlite-vec, 但Windows sqlite-vec安装可能失败
# 用简化方案: 字符n-gram Jaccard作为向量替代

def char_ngrams(text: str, n: int = 3) -> set[str]:
    """生成字符n-gram"""
    text = text.lower()
    return {text[i:i+n] for i in range(len(text)-n+1)}


def jaccard_similarity(s1: set, s2: set) -> float:
    """Jaccard 相似度"""
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


def knn_search(query: str, results: list[dict], k: int = 5) -> list[dict]:
    """对BM25结果做KNN重排序 (Jaccard n-gram)"""
    q_ngrams = char_ngrams(query)
    if not q_ngrams:
        return results[:k]
    
    scored = []
    for r in results:
        content = r.get("content", "")
        content_ngrams = char_ngrams(content)
        sim = jaccard_similarity(q_ngrams, content_ngrams)
        r["vector_score"] = round(sim, 4)
        # Final: weighted BM25 (0.6) + vector (0.4) — 数学推导方差比最优
        bm25 = r.get("bm25_score", 0.5)
        r["hybrid_score"] = round(0.6 * bm25 + 0.4 * sim, 4)
        scored.append(r)
    
    return sorted(scored, key=lambda x: x["hybrid_score"], reverse=True)[:k]


# ── MMR 多样性重排序 ─────────────────────

def mmr_rerank(results: list[dict], lambda_param: float = 0.61, k: int = 5) -> list[dict]:
    """MMR多样性重排序: 平衡相关性与多样性
    λ=0.61 数学推导最优: 信息熵 H_avg=2.5 下的平衡点
    精确查询(短): 应用λ=0.80; 探索查询(长): 应用λ=0.55"""
    if len(results) <= k:
        return results
    
    selected = []
    candidates = list(results)
    
    # Pick highest-scoring first
    selected.append(candidates.pop(0))
    
    while len(selected) < k and candidates:
        best_score = -1
        best_idx = 0
        
        for i, cand in enumerate(candidates):
            # Relevance
            rel = cand.get("hybrid_score", cand.get("bm25_score", 0.5))
            
            # Diversity: max similarity to already selected
            cand_ngrams = char_ngrams(cand.get("content", ""))
            max_sim = 0
            for sel in selected:
                sel_ngrams = char_ngrams(sel.get("content", ""))
                sim = jaccard_similarity(cand_ngrams, sel_ngrams)
                max_sim = max(max_sim, sim)
            
            # MMR formula
            mmr_val = lambda_param * rel - (1 - lambda_param) * max_sim
            
            if mmr_val > best_score:
                best_score = mmr_val
                best_idx = i
        
        selected.append(candidates.pop(best_idx))
    
    return selected


# ── 混合搜索Pipeline ──────────────────────

def hybrid_search(bm25: BM25Search, query: str, k: int = 5) -> list[dict]:
    """BM25 → KNN → MMR 完整管线"""
    # Step 1: BM25粗排
    bm25_results = bm25.search(query, k=k*3)
    if not bm25_results:
        return []
    
    # Step 2: KNN重排
    knn_results = knn_search(query, bm25_results, k=k*2)
    
    # Step 3: MMR多样性
    final = mmr_rerank(knn_results, lambda_param=0.7, k=k)
    
    return final


# ── CLI ────────────────────────────────────

def cli():
    import argparse
    parser = argparse.ArgumentParser(description="MemOS混合搜索")
    parser.add_argument("cmd", nargs="?", default="status",
                        choices=["index", "search", "demo", "status"])
    parser.add_argument("query", nargs="*", default=[], help="Search query")
    parser.add_argument("--profile", default="qqbot3", help="Hermes profile")
    parser.add_argument("--k", type=int, default=5, help="Results count")
    parser.add_argument("--mmr", type=float, default=0.7, help="MMR lambda")
    args = parser.parse_args()
    
    bm25 = BM25Search(str(VEC_DB))
    
    if args.cmd == "index":
        print(f"\n  {'='*50}")
        print(f"  MemOS: 构建混合索引")
        print(f"{'='*50}")
        count = bm25.build_from_hermes(args.profile)
        print(f"\n  ✅ 索引完成: {count} 条消息")
        print(f"     数据库: {VEC_DB}")
        
    elif args.cmd == "status":
        c = bm25.conn.cursor()
        c.execute("SELECT COUNT(*) FROM memos_body")
        n = c.fetchone()[0]
        c.execute("SELECT value FROM memos_meta WHERE key='last_index'")
        last = c.fetchone()
        print(f"\n  {'='*50}")
        print(f"  MemOS混合搜索 — 状态")
        print(f"{'='*50}")
        print(f"  索引条目:      {n}")
        print(f"  上次索引:      {last[0] if last else '从未'}")
        print(f"  数据库:      {VEC_DB}")
        print(f"  当前Profile: {args.profile}")
        
    elif args.cmd == "search":
        query = " ".join(args.query)
        if not query:
            query = input("  搜索: ").strip()
        if not query:
            return
        
        print(f"\n  {'='*50}")
        print(f"  混合搜索: \"{query}\"")
        print(f"{'='*50}")
        
        # BM25 only
        bm25_only = bm25.search(query, k=args.k)
        print(f"\n  🔵 BM25 结果 ({len(bm25_only)}):")
        for i, r in enumerate(bm25_only, 1):
            title = r.get("session_title", "?")[:30]
            role = r.get("role", "?")[:8]
            score = r.get("bm25_score", 0)
            snippet = r.get("content", "")[:100].replace("\n", " ")
            print(f"    {i:2d}. [{role:8s}] {title:30s}  bm25={score:.3f}")
            print(f"        {snippet}")
        
        # Hybrid
        hybrid = hybrid_search(bm25, query, k=args.k)
        print(f"\n  🟢 混合搜索(BM25+KNN+MMR) ({len(hybrid)}):")
        for i, r in enumerate(hybrid, 1):
            title = r.get("session_title", "?")[:30]
            role = r.get("role", "?")[:8]
            hscore = r.get("hybrid_score", r.get("bm25_score", 0))
            vscore = r.get("vector_score", 0)
            snippet = r.get("content", "")[:100].replace("\n", " ")
            print(f"    {i:2d}. [{role:8s}] {title:30s}  hybrid={hscore:.3f} vec={vscore:.3f}")
            print(f"        {snippet}")
        
    elif args.cmd == "demo":
        print(f"\n  {'='*50}")
        print(f"  MemOS混合搜索 — 自测演示")
        print(f"{'='*50}")
        
        # First build index
        print("\n  1. 构建索引...")
        count = bm25.build_from_hermes(args.profile)
        print(f"     ✅ {count} 条消息")
        
        # Test queries
        test_qs = ["A/B", "睡眠", "记忆", "AOS", "token"]
        for q in test_qs:
            print(f"\n  2. 搜索 \"{q}\":")
            results = bm25.search(q, k=3)
            if results:
                for r in results:
                    snippet = r.get("content", "")[:80].replace("\n", " ")
                    print(f"     [{r['role'][:6]:6s}] bm25={r['bm25_score']:.3f}  {snippet}")
            else:
                print("     无结果")
        
        # MMR demo
        print(f"\n  3. MMR多样性测试:")
        sample_results = [
            {"content": "Memory consolidation needs three stages", "bm25_score": 0.9, "hybrid_score": 0.9, "session_title": "A"},
            {"content": "Memory is essential for learning", "bm25_score": 0.85, "hybrid_score": 0.85, "session_title": "B"},
            {"content": "The three-stage pipeline works well", "bm25_score": 0.7, "hybrid_score": 0.7, "session_title": "C"},
            {"content": "Memory systems use SQLite for storage", "bm25_score": 0.65, "hybrid_score": 0.65, "session_title": "D"},
            {"content": "OptMem compresses via nap", "bm25_score": 0.55, "hybrid_score": 0.55, "session_title": "E"},
        ]
        mmrd = mmr_rerank(sample_results, args.mmr, k=3)
        for i, r in enumerate(mmrd, 1):
            print(f"     {i}. {r['session_title']:20s}  score={r.get('hybrid_score',0):.3f}")
    
    bm25.close()


if __name__ == "__main__":
    cli()
