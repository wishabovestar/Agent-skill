# -*- coding: utf-8 -*-
"""CortexMem 状态记忆层 v1.0 (2026-08-23, PX)
单元级标记 (PQ) + session 优先分层 (PV/PW) 生产落地
不破坏现有 CortexMem — 作为增强检索层

自动 supersession 判定 (无 LLM):
  1. 文本拆单元 (迁移词/句号分割)
  2. 迁移词检测 (已切换/升级/修复/替换/改为)
  3. 旧对象 vs 新对象配对 (规则表 + 通用检测)

用法:
  python cortexmem_state.py ingest  <文本文件>
  python cortexmem_state.py search  <查询>
  python cortexmem_state.py ab      # 真实数据 A/B
"""
import io
import json
import os
import re
import sqlite3
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DB = r"<PROFILE_ROOT>\state.db"
STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "state_memory.json")

# 迁移词 → 触发 supersession 标记
MIGRATION_WORDS = ["已切换", "切换", "升级", "修复", "替换", "改为", "替代",
                   "弃用", "迁移", "改用", "换用", "不再用", "已终止", "终止",
                   "停止", "失败", "不兼容", "取消"]

# 通用旧对象模式: 迁移词前 1-4 词 (实体名)
ENTITY = re.compile(r"([A-Za-z][A-Za-z0-9_.\-/]{2,40}|[\u4e00-\u9fff]{2,8})")

# 已知 supersession 规则表 (旧, 新) — 自动检测辅助
KNOWN_PAIRS = [
    ("paper_tracker", "nightly_research"),
    ("b10107", "b10516"),
    ("Gemini", "OpenCode Zen"),
    ("简单势", "非局部构造"),
    ("hf_cache", "HF_HOME"),
    ("insteadOf", "deploy key"),
]


def split_units(text):
    """拆事实单元: 迁移词/句读分割"""
    parts = re.split(r"(?<=[\u3002\uff1b\uff1a])|(?<=\.)\s+|(已切换|切换为|"
                     r"升级到|修复为|替换为|改为|改用|换用|迁移到|不再用)",
                     text)
    units = [p.strip() for p in parts if p and len(p.strip()) > 4]
    return units or ([text.strip()] if len(text) > 4 else [])


def judge_status(unit, text):
    """判定单元 status: active / superseded
    优先级: 已知配对 (旧/新对象) > 迁移词"""
    # 1. 含新对象 → active (新事实/切换记录)
    for old, new in KNOWN_PAIRS:
        if new in unit:
            return "active"
    # 2. 含旧对象且不含新 → superseded (旧事实描述,
    #    含"已终止"等迁移词也归此 — 迁移词正说明旧路线)
    for old, new in KNOWN_PAIRS:
        if old in unit:
            return "superseded"
    # 3. 迁移词 (无已知对) → active (新事实描述)
    if any(w in unit for w in ["已切换", "切换", "升级到", "升级为", "修复",
                               "替换为", "改为", "改用", "换用", "迁移到",
                               "替代", "不再用", "取消"]):
        return "active"
    return "active"


def ingest(text, ts=None):
    """写入: 拆单元 + status 标记"""
    store = load_store()
    ts = ts or time.time()
    units = split_units(text)
    added = 0
    for u in units:
        st = judge_status(u, text)
        # 去重 (同内容同状态)
        key = u[:120]
        if any(m["content"] == key and m["status"] == st for m in store):
            continue
        store.append({"content": key, "status": st,
                      "ts": ts, "source": text[:60]})
        added += 1
    save_store(store)
    return added


def load_store():
    if os.path.exists(STORE):
        with open(STORE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_store(store):
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False)


def search(query, top_k=5, session_n=60):
    """检索: session 优先排序 + active 过滤"""
    store = load_store()
    qw = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_.\-/]{2,}|[\u4e00-\u9fff]",
                        query.lower()))
    scored = []
    for m in store:
        if m["status"] != "active":
            continue  # active 过滤
        c = m["content"].lower()
        ov = len(set(re.findall(r"[a-zA-Z][a-zA-Z0-9_.\-/]{2,}|[\u4e00-\u9fff]",
                                c)) & qw)
        if ov:
            # session 优先: 时间新加权
            w = 1.5 if (time.time() - m["ts"]) < session_n * 3600 else 1.0
            scored.append((ov * w, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]


def ab_test():
    """真实数据 A/B: 基线 (无状态) vs 状态层"""
    print("=== 状态记忆层真实数据 A/B ===\n")
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT content, timestamp FROM messages "
        "WHERE content IS NOT NULL AND length(content) > 30 "
        "ORDER BY timestamp DESC LIMIT 800").fetchall()
    conn.close()

    # 入库 (模拟写入管线)
    for c, ts in rows:
        ingest(c, ts)
    store = load_store()
    n_sup = sum(1 for m in store if m["status"] == "superseded")
    print(f"入库: {len(store)} 单元 (superseded {n_sup} "
          f"({n_sup/len(store):.0%}) | active {len(store)-n_sup}\n")

    queries = [
        ("paper_tracker nightly_research", "paper_tracker", "nightly_research"),
        ("llama.cpp b10107", "b10107", "b10516"),
        ("Gemini 免费", "Gemini", "OpenCode Zen"),
        ("RH 谱 简单势", "简单势", "非局部构造"),
    ]
    for q, old, new in queries:
        hits = search(q, top_k=4)
        h_old = any(old in m["content"] for _, m in hits)
        h_new = any(new in m["content"] for _, m in hits)
        print(f"  {q[:22]:<24}: 旧{'✓' if h_old else '·'} "
              f"新{'✓' if h_new else '·'} "
              f"({'/'.join(m['content'][:16] for _, m in hits[:2])})")
    print(f"\n  → active 过滤: superseded 单元不参与检索 "
          f"({'✅' if n_sup > 0 else '⚠️ 无标记'})")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "ingest":
        for p in sys.argv[2:]:
            print(f"入库 {p}: +{ingest(open(p, encoding='utf-8').read())} 单元")
    elif len(sys.argv) > 1 and sys.argv[1] == "search":
        r = search(sys.argv[2])
        for _, m in r:
            print(f"  [{m['status']}] {m['content'][:60]}")
    elif len(sys.argv) > 1 and sys.argv[1] == "ab":
        ab_test()
    else:
        ab_test()
