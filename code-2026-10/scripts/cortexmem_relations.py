# -*- coding: utf-8 -*-
"""CortexMem 关系抽取 v1.0 (2026-08-14, Semantica TripletExtractor 借鉴)
SPO 三元组抽取: 语义节点 → (Subject, Predicate, Object) 关系边
写入 CortexMem state.db relations 表

用法: python cortexmem_relations.py <文本>
"""
# side_effects: [无写入, 输出]
import os, sys, io, re, sqlite3, datetime

STATE_DB = r"<PROFILE_ROOT>\knowledge_base\cortexmem\state.db"

# 轻量关系模式 (模式匹配, 零 LLM 依赖 — 本地可跑)
PATTERNS = [
    (r"([\u4e00-\u9fffA-Za-z0-9]{2,20})(?:是|为)([\u4e00-\u9fffA-Za-z0-9]{2,30})", "is_a"),
    (r"([\u4e00-\u9fffA-Za-z0-9]{2,20})(?:使用|采用|基于)([\u4e00-\u9fffA-Za-z0-9]{2,30})", "uses"),
    (r"([\u4e00-\u9fffA-Za-z0-9]{2,20})(?:依赖|需要|要求)([\u4e00-\u9fffA-Za-z0-9]{2,30})", "depends_on"),
    (r"([\u4e00-\u9fffA-Za-z0-9]{2,20})(?:提升|增强|改进)([\u4e00-\u9fffA-Za-z0-9]{2,30})", "improves"),
    (r"([\u4e00-\u9fffA-Za-z0-9]{2,20})(?:来自|源于)([\u4e00-\u9fffA-Za-z0-9]{2,30})", "originates_from"),
]


def extract_triplets(text):
    """模式抽取 SPO 三元组"""
    triplets = []
    for pat, rel in PATTERNS:
        for m in re.finditer(pat, text):
            s, o = m.group(1).strip(), m.group(2).strip()
            if s and o and s != o:
                triplets.append((s, rel, o))
    # 去重保序
    seen, out = set(), []
    for t in triplets:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def store(triplets, source=""):
    """写入 relations 表 (idempotent, [CL3] 带来源溯源)"""
    if not triplets:
        return 0
    conn = sqlite3.connect(STATE_DB)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS relations ("
                "subject TEXT, predicate TEXT, object TEXT, "
                "created TEXT, source TEXT, "
                "PRIMARY KEY(subject, predicate, object))")
    # [CL3-fix] 旧表迁移: 缺 source 列则补
    try:
        cur.execute("ALTER TABLE relations ADD COLUMN source TEXT")
        conn.commit()
    except Exception:
        pass  # 列已存在
    now = datetime.datetime.now().isoformat()
    n = 0
    for s, p, o in triplets:
        try:
            cur.execute("INSERT OR IGNORE INTO relations VALUES (?,?,?,?,?)",
                        (s, p, o, now, source[:200]))
            n += cur.rowcount
        except Exception:
            pass
    conn.commit()
    conn.close()
    return n


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        print("用法: python cortexmem_relations.py <文本>")
        sys.exit(1)
    text = sys.argv[1]
    trips = extract_triplets(text)
    print(f"🔗 抽取三元组: {len(trips)}")
    for s, p, o in trips[:10]:
        print(f"   {s} --({p})--> {o}")
    n = store(trips, source=text[:200])  # [CL3] 来源溯源
    print(f"💾 写入 relations: {n} 条")
