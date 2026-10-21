# -*- coding: utf-8 -*-
"""CortexMem Hermes 记忆流接入 v1.0 (2026-08-11)
从 Hermes state.db 自动摄取新会话消息 → CortexMem 三态入库
作为当前记忆库 (优胜组上线)

流程:
  1. 读取 state.db 最近 N 条新消息 (增量)
  2. 过滤: 用户消息→语义, 助手输出→情景, 错误/教训→高权重
  3. 写入 CortexMem (三态 + 倒排索引)
  4. 支持查询接口 (供 Hermes agent 调用)

用法:
  python cortexmem_integrate.py --sync      # 增量同步
  python cortexmem_integrate.py --query <q> # 查询
  python cortexmem_integrate.py --sleep     # 巩固
  python cortexmem_integrate.py --stats     # 状态
"""
# side_effects: [写数据文件]
import os, sys, io, json, sqlite3, time, re

# 注意: stdout 重配放 __main__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cortexmem import CortexMem, SEMANTIC, EPISODIC, PROCEDURAL

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "state.db")
CURSOR_FILE = os.path.join(BASE, "knowledge_base", "cortexmem", "sync_cursor.json")

# 高权重关键词 (错误/教训 → 提升权重)
HIGH_WEIGHT_WORDS = ["错误", "失败", "教训", "坑", "OOM", "修复", "bug", "崩溃", "超时", "无效"]

def get_cursor():
    if os.path.exists(CURSOR_FILE):
        try:
            return json.load(open(CURSOR_FILE, encoding="utf-8")).get("last_id", 0)
        except Exception:
            return 0
    return 0

def save_cursor(last_id):
    os.makedirs(os.path.dirname(CURSOR_FILE), exist_ok=True)
    json.dump({"last_id": last_id, "time": time.strftime("%Y-%m-%d %H:%M:%S")},
              open(CURSOR_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def sync_new_messages(limit=500):
    """增量同步: 从 state.db 摄取新消息"""
    mem = CortexMem()
    cursor = get_cursor()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, role, content, timestamp FROM messages "
        "WHERE id > ? AND content IS NOT NULL AND length(content) > 20 "
        "ORDER BY id ASC LIMIT ?", (cursor, limit)
    ).fetchall()
    conn.close()

    added = {"semantic": 0, "episodic": 0, "high_weight": 0}
    last_id = cursor
    for row in rows:
        content = row["content"][:500]
        role = row["role"]
        # 过滤工具输出噪音
        if content.startswith("MEDIA:") or content.startswith("{") and "tool" in content[:100]:
            continue
        if role == "user":
            mem.add(content, SEMANTIC)
            added["semantic"] += 1
        elif role == "assistant":
            mem.add(content, EPISODIC)
            added["episodic"] += 1
        # 高权重: 含错误/教训词 → 提升
        if any(w in content for w in HIGH_WEIGHT_WORDS):
            nid = mem._nid(content, SEMANTIC if role == "user" else EPISODIC)
            if nid in mem.state["nodes"]:
                mem.state["nodes"][nid]["weight"] = min(1.0, mem.state["nodes"][nid]["weight"] + 0.3)
                mem.state["nodes"][nid]["state"] = "hot"
                added["high_weight"] += 1
        last_id = row["id"]

    if added["semantic"] + added["episodic"] > 0:
        mem.save()
        save_cursor(last_id)
    return added, mem.stats()

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if "--sync" in sys.argv:
        # 支持 --limit N (恢复用大批量)
        lim = 500
        if "--limit" in sys.argv:
            lim = int(sys.argv[sys.argv.index("--limit") + 1])
        added, stats = sync_new_messages(limit=lim)
        print(f"🔄 CortexMem 同步:")
        print(f"   新增: 语义{added['semantic']} + 情景{added['episodic']} + 高权重{added['high_weight']}")
        print(f"   总节点: {stats['nodes']} | 状态: {stats['states']}")
    elif "--query" in sys.argv:
        i = sys.argv.index("--query")
        mem = CortexMem()
        q = " ".join(sys.argv[i+1:])
        results = mem.query(q)
        print(f"🔍 '{q}':")
        for r in results[:5]:
            print(f"  [{r['state']}/{r['type']}] {r['content'][:50]} (score={r['score']})")
    elif "--sleep" in sys.argv:
        mem = CortexMem()
        r = mem.sleep()
        mem.save()
        print(f"🌙 巩固: 蒸馏{r['distilled']} 聚类{r['clusters']} 剪枝{r['pruned']}")
        print(f"   {mem.stats()}")
    elif "--stats" in sys.argv:
        mem = CortexMem()
        print(f"📊 CortexMem: {mem.stats()}")
    else:
        print("用法: --sync | --query <q> | --sleep | --stats")
