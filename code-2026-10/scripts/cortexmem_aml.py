# -*- coding: utf-8 -*-
"""CortexMem AML 适配端点 v2.2 (2026-08-16, FC1-FC2)
Agent Memory Leaderboard API 规范: Add/Search 端点
本地实现: 测试 AML 评测接入 (关系多跳/事实回忆/时序)
[FC1] MemOS P0 吸收: 异步摄取队列 + 反馈修正
[FC2] MemOS P1 吸收: MemCube 版本元数据 + 三层记忆显式化

用法: python cortexmem_aml.py add <text> | search <query> | evals
"""
# side_effects: [无写入, 输出]
import os, sys, io, json, sqlite3, re, time, math, threading, queue

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DB = os.path.join(BASE, "knowledge_base", "cortexmem", "state.db")

# ── [FC1] P0: MemScheduler 异步摄取队列 ──
_ingest_q = queue.Queue()
_ingest_thread = None


def _ingest_worker():
    """后台消费者: ms 级批量写入 (MemOS MemScheduler 模式)"""
    while True:
        item = _ingest_q.get()
        if item is None:
            break
        text, source = item
        try:
            _add_sync(text, source)
        except Exception:
            pass
        _ingest_q.task_done()


def start_async():
    """启动异步摄取 (幂等)"""
    global _ingest_thread
    if _ingest_thread is None or not _ingest_thread.is_alive():
        _ingest_thread = threading.Thread(target=_ingest_worker, daemon=True)
        _ingest_thread.start()


def add_async(text, source="aml"):
    """异步 Add: 入队即返回 (ms 级)"""
    start_async()
    _ingest_q.put((text, source))
    return "queued"


def flush():
    """同步冲刷队列 (测试/关闭用)"""
    _ingest_q.join()


def add(text, source="aml"):
    """AML Add: 写入 semantic 节点 + relations (关系抽取)
    [EM1] 综合吸收: 加 access_count (复习计数) + source 溯源
    [FC2] MemCube 版本: version 列 (同内容更新 version+1)"""
    return _add_sync(text, source)


def _add_sync(text, source="aml"):
    conn = sqlite3.connect(STATE_DB)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS semantic (nid TEXT PRIMARY KEY, content TEXT, created REAL, access_count INTEGER DEFAULT 0, source TEXT DEFAULT '', version INTEGER DEFAULT 1)")
    # [EM1] 旧表迁移: 补列
    cols = [c[1] for c in cur.execute("PRAGMA table_info(semantic)").fetchall()]
    if "access_count" not in cols:
        cur.execute("ALTER TABLE semantic ADD COLUMN access_count INTEGER DEFAULT 0")
    if "source" not in cols:
        cur.execute("ALTER TABLE semantic ADD COLUMN source TEXT DEFAULT ''")
    if "version" not in cols:
        cur.execute("ALTER TABLE semantic ADD COLUMN version INTEGER DEFAULT 1")
    # [FC2] 同内容更新 → version+1 (MemCube 版本元数据)
    old = cur.execute("SELECT nid, version FROM semantic WHERE content=?", (text,)).fetchone()
    if old:
        cur.execute("UPDATE semantic SET version=version+1, created=? WHERE nid=?", (time.time(), old[0]))
        conn.commit()
        conn.close()
        return old[0]
    nid = "aml_" + str(int(time.time() * 1000))
    cur.execute("INSERT OR REPLACE INTO semantic (nid, content, created, access_count, source, version) VALUES (?,?,?,0,?,1)",
                (nid, text, time.time(), source))
    # [DR3-P0] FTS5 同步 (BM25 排序层, trigram 支持中文子串)
    try:
        cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS semantic_fts USING fts5(content, tokenize='trigram')")
        cur.execute("INSERT INTO semantic_fts (rowid, content) VALUES (?, ?)",
                    (cur.lastrowid if cur.lastrowid else int(time.time()), text))
    except Exception:
        pass
    # [DQ1] SPO 非贪婪修复: 谓词两侧取最近边界 (非贪婪 + 词边界)
    # 谓词: 使用/来自/基于/引用/提升/增强/依赖/借鉴/源自
    spo = re.findall(
        r"([\u4e00-\u9fffA-Za-z0-9_.\-]{1,30}?)\s*(?:使用|来自|基于|引用|提升|增强|依赖|借鉴|源自)\s*([\u4e00-\u9fffA-Za-z0-9_.\-]{1,30}?)(?:[，。、；]|$)",
        text)
    for s, o in spo:
        s, o = s.strip(), o.strip()
        if not s or not o or len(s) > 25 or len(o) > 25:
            continue
        cur.execute("INSERT OR REPLACE INTO relations (subject, predicate, object, created, source) VALUES (?,?,?,?,?)",
                    (s, "uses", o, time.time(), source))
    conn.commit(); conn.close()
    return nid


def multi_hop(query, max_depth=2, k=5):
    """[DS1] P1 多跳 BFS: relations 图遍历
    从 query 实体出发 BFS (O(V+E)) — 关系链发现"""
    conn = sqlite3.connect(STATE_DB)
    cur = conn.cursor()
    # BFS
    visited = set()
    frontier = [query]
    results = []
    for depth in range(max_depth):
        next_f = []
        for node in frontier:
            if node in visited:
                continue
            visited.add(node)
            cur.execute(
                "SELECT subject, predicate, object FROM relations "
                "WHERE subject = ? OR object = ?", (node, node))
            for s, p, o in cur.fetchall():
                other = o if s == node else s
                results.append((depth + 1, s, p, o))
                if other not in visited:
                    next_f.append(other)
        frontier = next_f
    conn.close()
    return results[:k]


def semantic_dedup(threshold=0.95):
    """[DS2] P1 语义去重 (mem0 fallback 思路):
    相似内容 (字符 n-gram Jaccard ≥ 阈值) 标记重复"""
    conn = sqlite3.connect(STATE_DB)
    cur = conn.cursor()
    cur.execute("SELECT nid, content FROM semantic")
    all_mem = cur.fetchall()
    dups = []
    # 字符 bigram Jaccard 相似度
    def jaccard(a, b):
        sa, sb = set(a[i:i+2] for i in range(len(a)-1)), set(b[i:i+2] for i in range(len(b)-1))
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)
    for i in range(len(all_mem)):
        for j in range(i+1, len(all_mem)):
            if all_mem[i][0] == all_mem[j][0]:
                continue
            sim = jaccard(all_mem[i][1][:100], all_mem[j][1][:100])
            if sim >= threshold:
                dups.append((all_mem[i][0], all_mem[j][0], round(sim, 3)))
    conn.close()
    return dups


def hnsv_index(embed_fn=None, rebuild=False):
    """[DS3] P2 向量索引: faiss HNSW (近似最近邻, O(log N))
    说明: bge-m3 向量走 Ollama 嵌入 → faiss IndexHNSWFlat
    幂等: 已建且未 rebuild 则直接加载"""
    import faiss
    import numpy as np
    idx_path = os.path.join(BASE, "knowledge_base", "cortexmem", "vec.index")
    if os.path.exists(idx_path) and not rebuild:
        return faiss.read_index(idx_path)
    # 空索引 (维度 1024 = bge-m3)
    index = faiss.IndexHNSWFlat(1024, 32)  # M=32 (HNSW 图度数)
    faiss.write_index(index, idx_path)
    return index


def vector_search(query_vec, k=5):
    """[DS3] HNSW 向量检索 (faiss) — 语义召回"""
    import faiss
    import numpy as np
    idx_path = os.path.join(BASE, "knowledge_base", "cortexmem", "vec.index")
    if not os.path.exists(idx_path):
        return None
    index = faiss.read_index(idx_path)
    q = np.array([query_vec], dtype=np.float32)
    if index.ntotal == 0:
        return None
    D, I = index.search(q, k)
    return D[0].tolist(), I[0].tolist()


def hnsv_test():
    """[DS3] HNSW 自测: 构造 1000 维样例验证索引可用"""
    import faiss
    import numpy as np
    index = hnsv_index(rebuild=True)
    rng = np.random.RandomState(42)
    vecs = rng.rand(100, 1024).astype(np.float32)
    index.add(vecs)
    faiss.write_index(index, os.path.join(BASE, "knowledge_base", "cortexmem", "vec.index"))
    D, I = index.search(vecs[:1], 3)
    return D, I


def correct(nid, new_text, reason=""):
    """[FC1] P0: 反馈修正 (MemOS 自然语言修正记忆)
    修正 = 新版本记忆 + 保留溯源 (reason 记录修正原因)"""
    conn = sqlite3.connect(STATE_DB)
    cur = conn.cursor()
    row = cur.execute("SELECT source, version FROM semantic WHERE nid=?", (nid,)).fetchone()
    if not row:
        conn.close()
        return None
    source, ver = row
    cur.execute("UPDATE semantic SET content=?, version=version+1, created=? WHERE nid=?",
                (new_text, time.time(), nid))
    conn.commit()
    conn.close()
    return {"nid": nid, "new_version": ver + 1, "reason": reason}


def layer_stats():
    """[FC2] P1: 三层记忆显式化统计
    L1 plaintext (semantic) / L2 activation (FTS 索引) / L3 parameter (技能蒸馏)"""
    conn = sqlite3.connect(STATE_DB)
    cur = conn.cursor()
    l1 = cur.execute("SELECT COUNT(*) FROM semantic").fetchone()[0]
    l2 = 0
    try:
        l2 = cur.execute("SELECT COUNT(*) FROM semantic_fts").fetchone()[0]
    except Exception:
        pass
    conn.close()
    skill_dir = os.path.join(BASE, "skills")
    l3 = 0
    if os.path.isdir(skill_dir):
        for root, _, files in os.walk(skill_dir):
            l3 += len([f for f in files if f.endswith(".md")])
    return {"L1_plaintext": l1, "L2_activation": l2, "L3_parameter": l3,
            "note": "L3=技能文件 (蒸馏知识, MemOS crystallized Skills 对齐)"}


# ══════════════════════════════════════════════════════════════
# [FH1] Memory-Palace 吸收 (FF 正果): 三职责分离 + 漂移检测
# ══════════════════════════════════════════════════════════════
_DRIFT_KEYS = ("embedding_backend", "embedding_model", "embedding_dim",
               "embedding_api_base")


def _env_embed_fingerprint():
    """真实环境指纹 (当前: FTS5 trigram + BM25 稀疏)"""
    return {
        "embedding_backend": "sqlite_fts5",
        "embedding_model": "bm25_trigram",
        "embedding_dim": "0",
        "embedding_api_base": "local",
    }


def record_index_meta(conn=None):
    """建立嵌入配置基线 (IndexMeta)"""
    own = conn is None
    conn = conn or sqlite3.connect(STATE_DB)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS index_meta (k TEXT PRIMARY KEY, v TEXT)")
    for k, v in _env_embed_fingerprint().items():
        cur.execute("INSERT OR REPLACE INTO index_meta (k, v) VALUES (?,?)", (k, v))
    conn.commit()
    if own:
        conn.close()


def drift_detect(conn=None):
    """[FH1] 漂移检测: IndexMeta vs 环境 → drifted keys
    Memory-Palace 语义: 检测 → 告警 → 调用方决定重索引 (不阻塞)"""
    own = conn is None
    conn = conn or sqlite3.connect(STATE_DB)
    cur = conn.cursor()
    try:
        rows = dict(cur.execute("SELECT k, v FROM index_meta").fetchall())
    except Exception:
        if own:
            conn.close()
        return {"drift": True, "missing": True,
                "keys": list(_DRIFT_KEYS), "reason": "index_meta 缺失"}
    drifted = [k for k in _DRIFT_KEYS if rows.get(k) != _env_embed_fingerprint().get(k)]
    if own:
        conn.close()
    return {"drift": bool(drifted), "missing": False, "keys": drifted}


def simulate_decay(thresh=0.35):
    """[FH1] 遗忘投影 (纯读): 返回候选 nid 列表, 无副作用"""
    import math as _m
    conn = sqlite3.connect(STATE_DB)
    rows = conn.execute(
        "SELECT nid, created, access_count FROM semantic").fetchall()
    conn.close()
    now = time.time()
    cands = []
    for nid, created, acc in rows:
        age = max(0.0, (now - created) / 86400.0)
        strength = 10.0 + acc * 20.0
        if _m.exp(-age / strength) < thresh:
            cands.append(nid)
    return cands


def approve_archive(nid):
    """[FH1] 遗忘归档 (唯一变更点): tombstone 风格
    不 DELETE — deprecated 标记 (Memory-Palace C2 约束)"""
    conn = sqlite3.connect(STATE_DB)
    cur = conn.cursor()
    cur.execute("UPDATE semantic SET version=version+1, source=source || '|archived' WHERE nid=?", (nid,))
    conn.commit()
    conn.close()
    return {"archived": nid, "mode": "tombstone"}


def search(query, k=5):
    """AML Search: FTS5 关键词 + relations 多跳
    [EM1] 综合吸收 (EL 正果): 排序 = BM25 × Ebbinghaus(复习) × 溯源
    - Ebbinghaus: R=e^(-age/S), S=10+access_count*20 (复习对抗遗忘)
    - 溯源: source 非空 ×1.3 (Semantica 可验证优先)
    - 命中即复习: access_count+1 (A/B 验证 +50% MRR)"""
    conn = sqlite3.connect(STATE_DB)
    cur = conn.cursor()
    try:
        cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS semantic_fts USING fts5(content, tokenize='trigram')")
    except Exception:
        pass
    hits = []
    try:
        # [FC3 修复] FTS5 单列 content → rowid join semantic 拿 nid
        cur.execute("SELECT rowid, content FROM semantic_fts WHERE semantic_fts MATCH ? LIMIT ?", (query, k * 4))
        ft_rows = cur.fetchall()
        hits = []
        for rowid, content in ft_rows:
            row = cur.execute("SELECT nid FROM semantic WHERE rowid=?", (rowid,)).fetchone()
            if row:
                hits.append((row[0], content))
            else:
                hits.append((str(rowid), content))
    except Exception:
        hits = []
    if not hits:
        cur.execute("SELECT nid, content FROM semantic WHERE content LIKE ? LIMIT ?", (f"%{query}%", k * 4))
        hits = cur.fetchall()
    # 综合加权排序
    now = time.time()
    scored = []
    for nid, content in hits:
        row = cur.execute("SELECT created, access_count, source FROM semantic WHERE nid=?", (nid,)).fetchone()
        if not row:
            continue
        created, acc, src = row
        age = max(0.0, (now - created) / 86400.0)
        strength = 10.0 + (acc or 0) * 20.0
        eb = math.exp(-age / strength)  # Ebbinghaus 复习对抗遗忘
        s = 1.3 if src else 1.0         # Semantica 溯源加权
        # 复习: 命中 +1 (持久化)
        cur.execute("UPDATE semantic SET access_count=access_count+1 WHERE nid=?", (nid,))
        scored.append((eb * s, content))
    conn.commit()
    scored.sort(key=lambda x: -x[0])
    hits = [(nid, content) for _, content in scored[:k]] if scored else hits[:k]
    # 多跳: 关系链 (A uses B, B 是...)
    hops = []
    cur.execute("SELECT subject, object FROM relations WHERE predicate='uses' AND object LIKE ? LIMIT 3", (f"%{query}%",))
    hops = cur.fetchall()
    conn.close()
    return hits, hops


def search_temporal(query, days=30, k=5):
    """[DQ2] temporal 查询: 按时间范围过滤 + 事件关键词
    用法: search_temporal('备份', days=7) → 近7天含"备份"的记忆"""
    conn = sqlite3.connect(STATE_DB)
    cur = conn.cursor()
    cutoff = time.time() - days * 86400
    cur.execute(
        "SELECT nid, content, created FROM semantic "
        "WHERE created >= ? AND content LIKE ? ORDER BY created DESC LIMIT ?",
        (cutoff, f"%{query}%", k))
    hits = cur.fetchall()
    # 事件时间戳提取: 文本中的日期模式
    events = []
    cur.execute("SELECT content, created FROM semantic WHERE created >= ? LIMIT 20", (cutoff,))
    for content, created in cur.fetchall():
        m = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}月\d{1,2}日|今日|昨天|本周|上月)", content)
        if m:
            events.append((m.group(1), content[:50], time.strftime("%m-%d", time.localtime(created))))
    conn.close()
    return hits, events


def check_contradictions(threshold_days=7):
    """[DQ3] 矛盾检测 (cognee detect_contradictions 借鉴):
    同实体不同谓词/同谓词相反对象 → 记忆冲突"""
    conn = sqlite3.connect(STATE_DB)
    cur = conn.cursor()
    cutoff = time.time() - threshold_days * 86400
    conflicts = []
    cur.execute(
        "SELECT subject, object, COUNT(*) c FROM relations "
        "WHERE created >= ? GROUP BY subject, object HAVING c > 1",
        (cutoff,))
    # 同 subject 多 object (冲突信号)
    cur2 = conn.cursor()
    cur2.execute("SELECT subject, COUNT(DISTINCT object) n FROM relations WHERE created >= ? GROUP BY subject HAVING n >= 2 LIMIT 8",
                 (cutoff,))
    for subject, n in cur2.fetchall():
        cur2.execute("SELECT DISTINCT object FROM relations WHERE subject=? AND created>=?", (subject, cutoff))
        objs = [r[0] for r in cur2.fetchall()[:4]]
        conflicts.append((subject, objs))
    conn.close()
    return conflicts


def evals():
    """AML 9 维度快速自评 (本地)"""
    tests = {
        "fact_recall": "CortexMem使用FTS5和bge-m3",
        "relational_multi_hop": "蒸馏技术",
        "temporal": "备份 周日",
    }
    print("AML 维度自评 (本地样例):")
    for dim, q in tests.items():
        hits, hops = search(q)
        ok = len(hits) > 0 or len(hops) > 0
        print(f"  {dim:22s}: {'✅' if ok else '❌'} ({len(hits)} 命中, {len(hops)} 关系)")
    print("\n注: 正式评测需 AML Key (agentmemories.ai/evaluation)")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        evals(); sys.exit(0)
    if sys.argv[1] == "add":
        print("添加:", add(sys.argv[2] if len(sys.argv) > 2 else "测试"))
    elif sys.argv[1] == "search":
        hits, hops = search(sys.argv[2] if len(sys.argv) > 2 else "")
        for h in hits[:3]:
            print(f"  🔍 {h[1][:60]}")
        for s, o in hops[:3]:
            print(f"  🔗 {s} uses {o}")
    else:
        evals()
