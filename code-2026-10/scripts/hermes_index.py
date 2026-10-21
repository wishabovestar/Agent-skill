# -*- coding: utf-8 -*-
"""Hermes 统一混合索引 v2.0 (2026-08-08, 借鉴 MemOS hybrid retrieval + graphify graph)
三源索引: skills (SKILL.md) + knowledge_base + 会话记忆 (state.db)
检索: FTS5 (SQLite BM25) + 向量 (bge-m3) + RRF 融合
用法:
  python hermes_index.py --rebuild        # 重建全部索引
  python hermes_index.py --index-skills   # 增量索引 skills
  python hermes_index.py --search "查询"  # 混合检索 (FTS+向量+RRF)
  python hermes_index.py --search "查询" --fts-only  # 仅 FTS (快)
"""
# side_effects: [写数据文件]
import sqlite3, os, io, sys, json, glob, re, time, math, hashlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROFILE = r"<PROFILE_ROOT>"
KB = os.path.join(PROFILE, "knowledge_base")
SKILLS = os.path.join(PROFILE, "skills")
STATE_DB = os.path.join(PROFILE, "state.db")
INDEX_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hermes_index.db")
OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "bge-m3"

# 索引源权重 (RRF 融合时各源偏好)
SOURCE_WEIGHT = {"skill": 1.5, "kb": 1.0, "session": 0.8}


class HermesIndex:
    def __init__(self, rebuild=False):
        self.conn = sqlite3.connect(INDEX_DB)
        self._emb_cache = {}
        self._init_schema(rebuild)

    def _init_schema(self, rebuild):
        cur = self.conn.cursor()
        if rebuild:
            cur.execute("DROP TABLE IF EXISTS hermes_fts")
            cur.execute("DROP TABLE IF EXISTS docs")
        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS hermes_fts USING fts5(
                doc_id, title, content, source, tokenize='unicode61'
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS docs(
                id INTEGER PRIMARY KEY, path TEXT UNIQUE, mtime REAL,
                title TEXT, source TEXT
            )
        """)
        self.conn.commit()
        if rebuild:
            self.rebuild_all()

    def _index_file(self, cur, path, source, content):
        """索引单个文件 (按 3000 字符分块)"""
        mtime = os.path.getmtime(path)
        title = os.path.basename(path)
        row = cur.execute("SELECT id, mtime FROM docs WHERE path=?", (path,)).fetchone()
        if row and row[1] == mtime:
            return 0
        if row:
            cur.execute("DELETE FROM hermes_fts WHERE doc_id=?", (row[0],))
            cur.execute("UPDATE docs SET mtime=? WHERE id=?", (mtime, row[0]))
            doc_id = row[0]
        else:
            cur.execute("INSERT INTO docs(path, mtime, title, source) VALUES(?,?,?,?)",
                        (path, mtime, title, source))
            doc_id = cur.lastrowid
        n = 0
        for i in range(0, len(content), 3000):
            chunk = content[i:i+3000]
            cur.execute("INSERT INTO hermes_fts(doc_id, title, content, source) VALUES(?,?,?,?)",
                        (doc_id, title, chunk, source))
            n += 1
        return n

    def index_skills(self):
        """索引 skills (SKILL.md 全部)"""
        cur = self.conn.cursor()
        n = 0
        for f in glob.glob(os.path.join(SKILLS, "**", "SKILL.md"), recursive=True):
            try:
                content = open(f, encoding="utf-8", errors="replace").read()
                n += self._index_file(cur, f, "skill", content)
            except Exception:
                continue
        self.conn.commit()
        return n

    def index_kb(self):
        """索引 knowledge_base (md + json 知识条目)

        ★★★ 修复 (R1125, 2026-09-16): 原版【只扫 **/*.md】→
        巡天采集的知识条目 (kb_*.json, 2,700+ 条) 【从未进入索引】,
        检索完全不可达 (实测: 查询新采集论文 → 0 命中)。
        """
        cur = self.conn.cursor()
        n = 0
        for f in glob.glob(os.path.join(KB, "**", "*.md"), recursive=True):
            try:
                content = open(f, encoding="utf-8", errors="replace").read()
                if len(content) < 100:
                    continue
                n += self._index_file(cur, f, "kb", content)
            except Exception:
                continue
        # ★ 新增: json 知识条目 (巡天采集的各域 kb_*.json)
        for f in glob.glob(os.path.join(KB, "**", "*.json"), recursive=True):
            try:
                d = json.load(open(f, encoding="utf-8"))
                text = self._json_entry_text(d)
                if len(text) < 100:
                    continue          # 非知识条目 (registry/空结构) 跳过
                n += self._index_file(cur, f, "kb-xuntian", text)
            except Exception:
                continue
        self.conn.commit()
        return n

    @staticmethod
    def _json_entry_text(d):
        """把巡天 json 知识条目转为可检索文本 (R1125)"""
        if not isinstance(d, dict):
            return ""
        parts = []
        for k in ("title", "summary_cn", "summary", "abstract"):
            v = d.get(k)
            if v:
                parts.append(str(v))
        for k in ("key_techniques", "tags"):
            v = d.get(k)
            if isinstance(v, list) and v:
                parts.append(" ".join(str(x) for x in v))
        for k in ("url", "domain", "collected_at"):
            v = d.get(k)
            if v:
                parts.append(str(v))
        return "\n".join(parts)

    def index_sessions(self):
        """索引会话记忆 (state.db 用户消息, 每条会话摘要)"""
        if not os.path.exists(STATE_DB):
            return 0
        cur = self.conn.cursor()
        n = 0
        try:
            conn = sqlite3.connect(STATE_DB)
            conn.row_factory = sqlite3.Row
            # 每个会话聚合用户消息为一条记忆
            rows = conn.execute("""
                SELECT session_id, GROUP_CONCAT(content, ' ') as text
                FROM messages WHERE role='user' AND content IS NOT NULL
                GROUP BY session_id
            """).fetchall()
            conn.close()
            for r in rows:
                text = (r["text"] or "")[:5000]
                if len(text) < 80:
                    continue
                path = f"session://{r['session_id']}"
                mtime = time.time()
                row = cur.execute("SELECT id FROM docs WHERE path=?", (path,)).fetchone()
                if row:
                    cur.execute("DELETE FROM hermes_fts WHERE doc_id=?", (row[0],))
                    cur.execute("UPDATE docs SET mtime=? WHERE id=?", (mtime, row[0]))
                    doc_id = row[0]
                else:
                    cur.execute("INSERT INTO docs(path, mtime, title, source) VALUES(?,?,?,?)",
                                (path, mtime, r["session_id"][:24], "session"))
                    doc_id = cur.lastrowid
                for i in range(0, len(text), 3000):
                    cur.execute("INSERT INTO hermes_fts(doc_id, title, content, source) VALUES(?,?,?,?)",
                                (doc_id, r["session_id"][:24], text[i:i+3000], "session"))
                    n += 1
        except Exception as e:
            print(f"  会话索引警告: {e}")
        self.conn.commit()
        return n

    def rebuild_all(self):
        print("重建索引:")
        print(f"  skills: {self.index_skills()} 块")
        print(f"  kb: {self.index_kb()} 块")
        print(f"  sessions: {self.index_sessions()} 块")

    def fts_search(self, query, top_k=8):
        """FTS5 BM25 检索 (带源加权, 中文按 2 字 bigram 拆词)"""
        tokens = []
        # 中文: 按 2 字滑动窗口拆词 (FTS5 unicode61 对中文按字切分, bigram 召回更好)
        for seg in re.findall(r"[\u4e00-\u9fff]+", query):
            if len(seg) == 1:
                tokens.append(seg)
            else:
                tokens.extend(seg[i:i+2] for i in range(len(seg) - 1))
        # 英文: 保留单词
        tokens.extend(re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]{2,}", query))
        # 本体扩展 (context-ontology 借鉴): 同义词/下位词提升语义召回
        try:
            import sys as _sys, os as _os
            onto_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "hermes_ontology.py")
            if _os.path.exists(onto_path):
                _sys.path.insert(0, _os.path.dirname(onto_path))
                from hermes_ontology import expand_query
                tokens.extend(expand_query(query))
        except Exception:
            pass
        # 单字 token 会导致噪声, 过滤单字 (除非是关键词)
        tokens = [t for t in tokens if len(t) >= 2 or t in ("锂", "硅", "碳", "AI")]
        fts_q = " OR ".join(f'"{t}"' for t in tokens[:10])
        if not fts_q:
            return []
        try:
            cur = self.conn.cursor()
            rows = cur.execute("""
                SELECT d.path, d.title, d.source,
                       snippet(hermes_fts, 2, '[', ']', '...', 10) as snip,
                       bm25(hermes_fts) as score
                FROM hermes_fts JOIN docs d ON hermes_fts.doc_id = d.id
                WHERE hermes_fts MATCH ?
                ORDER BY score LIMIT ?
            """, (fts_q, top_k * 3)).fetchall()
            # 去重 + 源加权
            seen = set()
            results = []
            for path, title, source, snip, score in rows:
                if path in seen:
                    continue
                seen.add(path)
                weighted = -score * SOURCE_WEIGHT.get(source, 1.0)
                results.append((source, path, snip or title, weighted))
            # M1 正交优化: 勒贝格分层重排 (值域分层, 平滑尖峰, 保持排名)
            try:
                import os as _os, sys as _sys
                _lp = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "lebesgue_scoring.py")
                if _os.path.exists(_lp):
                    _sys.path.insert(0, _os.path.dirname(_lp))
                    from lebesgue_scoring import lebesgue_rerank
                    # 对加权分做分层重排, 返回 top_k
                    ranked = lebesgue_rerank([(r[1], r[3]) for r in results], top_k=top_k)
                    by_path = {r[1]: r for r in results}
                    results = [by_path[d] for d, _ in ranked if d in by_path]
                else:
                    results = results[:top_k]
            except Exception:
                results = results[:top_k]
            return results
        except Exception:
            return []

    def fts_search_raw(self, query, top_k=8):
        """FTS5 检索返回原始 BM25 分数 (不加权, 供勒贝格分层评分用)"""
        tokens = []
        import re as _re
        for seg in _re.findall(r"[\u4e00-\u9fff]+", query):
            if len(seg) == 1:
                tokens.append(seg)
            else:
                tokens.extend(seg[i:i+2] for i in range(len(seg) - 1))
        tokens.extend(_re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]{2,}", query))
        tokens = [t for t in tokens if len(t) >= 2 or t in ("锂", "硅", "碳", "AI")]
        fts_q = " OR ".join(f'"{t}"' for t in tokens[:10])
        if not fts_q:
            return []
        try:
            cur = self.conn.cursor()
            rows = cur.execute("""
                SELECT d.path, d.source, bm25(hermes_fts) as score
                FROM hermes_fts JOIN docs d ON hermes_fts.doc_id = d.id
                WHERE hermes_fts MATCH ?
                ORDER BY score LIMIT ?
            """, (fts_q, top_k)).fetchall()
            # 去重
            seen = set()
            results = []
            for path, source, score in rows:
                if path in seen:
                    continue
                seen.add(path)
                results.append((path, source, float(score)))
            return results
        except Exception:
            return []

    def embed(self, text, cache_key=None):
        """bge-m3 嵌入 (带内存缓存)"""
        if cache_key is not None:
            cached = self._emb_cache.get(cache_key)
            if cached:
                return cached
        try:
            import urllib.request
            req = urllib.request.Request(OLLAMA_EMBED_URL,
                data=json.dumps({"model": EMBED_MODEL, "input": text[:1500]}).encode(),
                headers={"Content-Type": "application/json"})
            resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
            emb = resp.get("embeddings", [None])[0]
            if cache_key is not None and emb:
                self._emb_cache[cache_key] = emb
            return emb
        except Exception:
            return None

    def vector_search(self, query, top_k=5):
        """向量检索 (bge-m3, 对候选文档嵌入比较, 限 40 文档保速度)"""
        q_emb = self.embed(query)
        if not q_emb:
            return []
        cur = self.conn.cursor()
        # 取文档首块 (限制 40 个避免过慢)
        docs = cur.execute("""
            SELECT d.id, d.path, d.title, d.source, hf.content
            FROM docs d JOIN hermes_fts hf ON d.id = hf.doc_id
            GROUP BY d.id LIMIT 40
        """).fetchall()
        results = []
        for doc_id, path, title, source, content in docs:
            d_emb = self.embed((content or "")[:1000], cache_key=f"doc_{doc_id}")
            if not d_emb:
                continue
            dot = sum(a*b for a, b in zip(q_emb, d_emb))
            nq = math.sqrt(sum(a*a for a in q_emb)) or 1
            nd = math.sqrt(sum(b*b for b in d_emb)) or 1
            sim = dot / (nq * nd)
            if sim > 0.32:
                results.append((source, path, title, sim * SOURCE_WEIGHT.get(source, 1.0)))
        results.sort(key=lambda x: -x[3])
        return results[:top_k]

    def hybrid_search(self, query, top_k=8, use_vector=True):
        """混合检索: FTS + 向量 + RRF 融合"""
        fts = self.fts_search(query, top_k)
        vec = self.vector_search(query, top_k) if use_vector else []
        rrf = {}
        for rank, (src, path, snip, score) in enumerate(fts + vec):
            rrf.setdefault(path, {"src": src, "snip": snip, "rrf": 0.0, "score": score})
            rrf[path]["rrf"] += 1.0 / (60 + rank + 1)
            rrf[path]["score"] = max(rrf[path]["score"], score)
        ranked = sorted(rrf.items(), key=lambda x: -x[1]["rrf"])
        return [(v["src"], k, v["snip"], v["rrf"]) for k, v in ranked[:top_k]]


def main():
    args = sys.argv[1:]
    idx = HermesIndex(rebuild="--rebuild" in args)
    if "--index-skills" in args:
        n = idx.index_skills()
        print(f"增量索引 skills: {n} 块")
    elif "--index-kb" in args:
        # ★ R1098: 增量索引 knowledge_base (index_kb 本身按 mtime 去重)
        n = idx.index_kb()
        print(f"增量索引 knowledge_base: {n} 块")
    elif "--search" in args:
        i = args.index("--search")
        query = args[i+1] if i+1 < len(args) else "锂电池"
        use_vec = "--fts-only" not in args
        print(f"🔍 {query} ({'FTS+向量+RRF' if use_vec else 'FTS only'})")
        results = idx.hybrid_search(query, use_vector=use_vec)
        for src, path, snip, score in results:
            tag = {"skill": "🛠", "kb": "📚", "session": "💬"}.get(src, "📄")
            print(f"  {tag} [{src}] {os.path.basename(path)} (rrf={score:.4f})")
            print(f"    {snip[:70]}")
        if not results:
            print("  (无结果)")
    else:
        print("用法: --rebuild | --index-skills | --search '查询' [--fts-only]")


if __name__ == "__main__":
    main()
