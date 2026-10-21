# -*- coding: utf-8 -*-
"""新旧记忆库 A/B 对比 v1.0 (2026-08-11)
对比: 旧 (FTS5/BM25) vs 新 (CortexMem)

指标:
  1. 检索命中率 (真实查询)
  2. 30天保持率 (模拟)
  3. 节点增长 (CortexMem 演化)
  4. 隔离拦截数 (安全)

输出: knowledge_base/audit/cortexmem_ab_YYYYMMDD.json
"""
# side_effects: [写数据文件]
import os, sys, io, json, datetime, sqlite3, re

# [修复] stdout 重配移入 __main__ (herdr State/Runtime 分离)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cortexmem import CortexMem

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "state.db")
AUDIT = os.path.join(BASE, "knowledge_base", "audit")
QUARANTINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cortexmem_quarantine.json")

# 旧库基线 (来自历史验证)
BASELINE_30D = 0.331

def _words(text):
    return set(re.findall(r'[a-zA-Z]{3,}|[\u4e00-\u9fff]{1}', text.lower()))

def fts5_retrieve(memories, query, top_k=5):
    q_words = _words(query)
    if not q_words:
        return []
    scored = []
    for m in memories:
        overlap = len(_words(m) & q_words)
        if overlap > 0:
            scored.append((overlap, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:top_k]]

def load_memories(limit=100):
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT content FROM messages WHERE role='assistant' AND content IS NOT NULL "
        "AND length(content) > 50 ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [r[0][:300] for r in rows]

def load_queries(limit=20):
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT content FROM messages WHERE role='user' AND content IS NOT NULL "
        "AND length(content) > 10 AND length(content) < 60 ORDER BY timestamp DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows if r[0] and len(r[0]) > 5]

def compare():
    mem = CortexMem()
    memories = load_memories(100)
    queries = load_queries(20)

    # 1. 检索命中率
    fts5_hits, cortex_hits = 0, 0
    for q in queries:
        fts = fts5_retrieve(memories, q)
        qw = _words(q)
        if any(len(_words(m) & qw) >= 2 for m in fts):
            fts5_hits += 1
        cx = mem.query(q, 5)
        if any(len(_words(r["content"]) & qw) >= 2 for r in cx):
            cortex_hits += 1

    # 2. 30天模拟
    sim = mem.simulate_30d()

    # 3. 节点统计
    stats = mem.stats()

    # 4. 隔离拦截
    quarantined = 0
    if os.path.exists(QUARANTINE):
        try:
            quarantined = len(json.load(open(QUARANTINE, encoding="utf-8")))
        except Exception:
            quarantined = 0

    result = {
        "date": datetime.date.today().isoformat(),
        "retrieval": {
            "fts5_baseline": f"{fts5_hits}/{len(queries)} ({fts5_hits/max(len(queries),1):.0%})",
            "cortexmem": f"{cortex_hits}/{len(queries)} ({cortex_hits/max(len(queries),1):.0%})",
        },
        "retention_30d": {
            "baseline": BASELINE_30D,
            "cortexmem": round(sim, 3),
            "improvement": f"{sim/BASELINE_30D:.2f}x",
        },
        "cortex_stats": stats,
        "security": {"quarantined": quarantined},
        "eval_7dims": _eval_7dims_snapshot(),  # [Z2] 7 论文维度 (2026-08-13)
    }

    os.makedirs(AUDIT, exist_ok=True)
    path = os.path.join(AUDIT, f"cortexmem_ab_{result['date']}.json")
    if os.path.exists(path):
        if os.path.exists(path + ".bak"):
            try: os.remove(path + ".bak")
            except OSError: pass
        os.rename(path, path + ".bak")
    json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return result, path

def _eval_7dims_snapshot():
    """[Z2] 7 论文评估维度快照 (加入周度 A/B 输出)"""
    try:
        from memory_param_validate import eval_7dims
        import io as _io, sys as _sys
        old = _sys.stdout
        _sys.stdout = _io.StringIO()  # 静默捕获打印
        try:
            mem = CortexMem()
            score = eval_7dims(mem, "A/B")
        finally:
            _sys.stdout = old
        return {"score": f"{score}/7", "detail": [
            "超限恢复", "链接追踪", "反思蒸馏", "技能晶体",
            "反馈响应", "生命周期", "长程查询"][:score]}
    except Exception as e:
        return {"score": "err", "error": str(e)[:60]}


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    result, path = compare()
    print("═" * 55)
    print(f"CortexMem vs 旧库 A/B 对比 ({result['date']})")
    print("═" * 55)
    r = result["retrieval"]
    print(f"🔍 检索命中: 旧FTS5 {r['fts5_baseline']} | CortexMem {r['cortexmem']}")
    t = result["retention_30d"]
    print(f"📊 30天保持: 旧 {t['baseline']} | CortexMem {t['cortexmem']} ({t['improvement']})")
    print(f"🧠 CortexMem: {result['cortex_stats']['nodes']} 节点 "
          f"{result['cortex_stats']['types']}")
    print(f"🛡️ 安全隔离: {result['security']['quarantined']} 条")
    print(f"\n📄 报告: {path}")
