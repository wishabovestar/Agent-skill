#!/usr/bin/env python3
"""
CoMem 机制③ A/B 实测 — 多样性过滤检索 vs 现行单流 top-k
════════════════════════════════════════════════════════════════
借鉴来源: CoMem (arXiv 2609.15009v1) §3.4 Parallel Dual-Stream Retrieval
  · 原文: "group semantically similar candidates into clusters, and then
          select the most representative entry from each cluster"
  · 动机: 扁平 top-k 按打分排序 → 返回【近似重复】条目, 上下文冗余
  · 原文证据: 共享记忆【常不如无记忆】(G-Memory 59.53 vs No-mem 67.78)

本机缺口 (实测):
  scripts/cortexmem.py query() L391-435 为【单流】打分:
    score = sim * weight * boost * fb_boost * (1+access) → top_k 直取
  → 无聚类 / 无多样性 / 无去冗余

A/B 设计 (真实数据, 禁虚构):
  A 基线: 现行单流 top-5 (复刻 query() 打分, 只读不改 state)
  B 处理: top-N 候选 → 层次聚类 → 每簇取代表 → top-5
  数据: knowledge_base/cortexmem/state.json (14,458 真实节点)
  查询: 从真实节点抽样 (真实内容分布), N=60
  度量: bge-m3 真实 embedding 余弦
    · 冗余度 = top-k 内平均两两余弦 (↓ 越好)
    · 多样性 = top-k 覆盖的语义簇数 (↑ 越好)
  ★ 参数扫描: 聚类阈值 × 候选池大小 (单次运行内完成, 嵌入只算一遍)
"""
# side_effects: [读 state.json 只读, 写 A/B 报告 json]

import os, sys, json, math, random, time, urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(BASE, "knowledge_base", "cortexmem", "state.json")
OUT = os.path.join(BASE, "knowledge_base", "research", "comem_ab_result.json")

N_QUERIES = 60
K = 5
POOL_MAX = 40
# ★ 参数扫描: (聚类阈值, 候选池大小)
CONFIGS = [(0.50, 20), (0.60, 20), (0.70, 20), (0.80, 20), (0.60, 40), (0.70, 40)]
EMB_BATCH = 24

_WORD_RE = None
def words(text):
    global _WORD_RE
    if _WORD_RE is None:
        import re
        _WORD_RE = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]")
    return set(_WORD_RE.findall((text or "").lower()))


def embed_batch(texts):
    payload = json.dumps({"model": "bge-m3",
                          "input": [t[:500] for t in texts]}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/embed", data=payload,
                                 headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=120).read())
    return d.get("embeddings") or []


def cosine(a, b):
    if not a or not b:
        return 0.0
    s = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return s / (na * nb) if na and nb else 0.0


def score_node(node, q_words, q_entities):
    """复刻 cortexmem.query() 打分 (只读)"""
    w = words(node["content"])
    sim = len(w & q_words)
    if sim == 0:
        return 0.0
    boost = {"hot": 1.5, "warm": 1.2, "cold": 1.0}.get(node.get("state"), 1.0)
    fb_boost = 1.0 if node.get("feedback", 0) >= 0 else 0.85
    s = sim * node.get("weight", 1.0) * boost * fb_boost * \
        (1 + min(0.5, node.get("access", 0) * 0.05))
    if node.get("velocity") == "volatile":
        age = (time.time() - node.get("last_access", time.time())) / 86400
        s *= max(0.3, 1.0 - age * 0.15)
    else:
        s *= 1.05
    if node.get("entity"):
        s *= 1.3
    elif q_entities and any(e.lower() in node["content"].lower() for e in q_entities):
        s *= 1.2
    if node.get("crystal", 0) > 1:
        s *= 1 + min(0.3, node["crystal"] * 0.05)
    return s


def cluster(embs, thresh):
    """单链层次聚类 (阈值合并) → 簇标签"""
    n = len(embs)
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i in range(n):
        for j in range(i + 1, n):
            if cosine(embs[i], embs[j]) >= thresh:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
    remap, out = {}, []
    for i in range(n):
        l = find(i)
        if l not in remap:
            remap[l] = len(remap)
        out.append(remap[l])
    return out


def main():
    t0 = time.time()
    st = json.load(open(STATE, encoding="utf-8"))
    nodes = st["nodes"]
    print("  载入真实节点: %d" % len(nodes))

    inverted = {}
    for nid, nd in nodes.items():
        for w in words(nd["content"]):
            inverted.setdefault(w, set()).add(nid)
    print("  倒排索引词条: %d" % len(inverted))

    random.seed(20260916)
    sample = random.sample(list(nodes.keys()), min(N_QUERIES, len(nodes)))

    res_A, res_B = [], {}
    deg_count = [0]
    emb_cache = {}

    def get_embs(texts):
        need = [t for t in texts if t[:500] not in emb_cache]
        for i in range(0, len(need), EMB_BATCH):
            chunk = need[i:i + EMB_BATCH]
            try:
                for t, e in zip(chunk, embed_batch(chunk)):
                    emb_cache[t[:500]] = e
            except Exception:
                for t in chunk:
                    emb_cache.setdefault(t[:500], None)
        return [emb_cache.get(t[:500]) for t in texts]

    def metrics(sel):
        """返回 (冗余度, 语义簇数, 有效条目数)"""
        if len(sel) < 2:
            return 0.0, len(sel), 0
        ems = [e for e in get_embs([nodes[n]["content"][:500] for n in sel]) if e]
        if len(ems) < 2:
            return 0.0, len(ems), 0
        ps = [cosine(ems[i], ems[j])
              for i in range(len(ems)) for j in range(i + 1, len(ems))]
        return sum(ps) / len(ps), len(set(cluster(ems, 0.80))), len(ems)

    used = 0
    for qi, qid in enumerate(sample):
        q = nodes[qid]["content"][:200]
        qw = words(q)
        cand = set()
        for w in qw:
            cand |= inverted.get(w, set())
        cand.discard(qid)
        if len(cand) < K:
            continue
        scored = [(s, nid) for nid in cand
                  if (s := score_node(nodes[nid], qw, [])) > 0]
        if len(scored) < K:
            continue
        scored.sort(key=lambda x: -x[0])
        pool = scored[:POOL_MAX]
        A = [nid for _, nid in pool[:K]]           # 基线 (池内 top-K)
        used += 1

        texts = [nodes[nid]["content"][:500] for _, nid in pool]
        embs = get_embs(texts)
        if any(e is None for e in embs):
            deg_count[0] += 1
            for key in CONFIGS:
                res_B.setdefault(key, []).append((0.0, 0, 0))
        else:
            for (thresh, pool_n) in CONFIGS:
                sub, sub_embs = pool[:pool_n], embs[:pool_n]
                labels = cluster(sub_embs, thresh)
                cl = {}
                for idx, lab in enumerate(labels):
                    cl.setdefault(lab, []).append(idx)
                B, seen = [], set()
                order = sorted(cl.keys(), key=lambda l: cl[l][0])
                while len(B) < K and len(seen) < len(sub):
                    for lab in order:
                        for idx in cl[lab]:
                            if idx not in seen:
                                B.append(sub[idx][1]); seen.add(idx); break
                        if len(B) >= K:
                            break
                res_B.setdefault((thresh, pool_n), []).append(metrics(B))

        res_A.append(metrics(A))
        if (qi + 1) % 15 == 0:
            print("    进度 %d/%d" % (qi + 1, len(sample)))

    def agg(rs):
        if not rs:
            return (0.0, 0.0, 0.0)
        return (sum(r[0] for r in rs) / len(rs),
                sum(r[1] for r in rs) / len(rs),
                sum(r[2] for r in rs) / len(rs))

    ra, ca, na = agg(res_A)
    print("\n  ═══ A/B 参数扫描 (n=%d 有效查询, 降级 %d) ═══" % (used, deg_count[0]))
    print("  %-18s %-10s %-10s %-10s %-10s %s"
          % ("配置(阈值,池)", "冗余度↓", "簇数↑", "冗余降幅", "多样性增益", "判定"))
    print("  %-18s %-10.4f %-10.3f %-10s %-10s %s"
          % ("A 单流基线", ra, ca, "—", "—", "基线"))
    rows, best = [], None
    for (thresh, pool_n) in CONFIGS:
        rb, cb, nb = agg(res_B.get((thresh, pool_n), []))
        if not ra or not cb:
            continue
        drop = (ra - rb) / ra
        gain = (cb - ca) / ca if ca else 0.0
        v = ("✅ 增益成立" if (drop >= 0.10 and gain > 0)
             else ("🟡 增益微弱" if drop > 0.02 else "🔴 无增益"))
        print("  %-18s %-10.4f %-10.3f %-10s %-10s %s"
              % ("(%.2f, %d)" % (thresh, pool_n), rb, cb, "↓%.1f%%" % (drop * 100),
                 "↑%.1f%%" % (gain * 100), v))
        rows.append({"thresh": thresh, "pool": pool_n, "redundancy": round(rb, 4),
                     "clusters": round(cb, 3), "drop_pct": round(drop * 100, 2),
                     "diversity_gain_pct": round(gain * 100, 2), "verdict": v})
        if best is None or drop > best["drop_pct"] / 100:
            best = rows[-1]

    print("\n  ★ 基线冗余度 %.4f (top-5 内平均两两余弦) — %s"
          % (ra, "冗余确实偏高" if ra > 0.45 else "冗余不高"))
    if best:
        print("  ★ 最优配置: (%.2f, %d) → 冗余 ↓%.1f%% / 多样性 ↑%.1f%% → %s"
              % (best["thresh"], best["pool"], best["drop_pct"],
                 best["diversity_gain_pct"], best["verdict"]))

    json.dump({"n_queries": used, "K": K, "pool_max": POOL_MAX,
               "A_baseline": {"redundancy": round(ra, 4), "clusters": round(ca, 3)},
               "sweep": rows, "best": best, "degraded": deg_count[0],
               "elapsed_sec": round(time.time() - t0, 1)},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n  💾 %s | 耗时 %.1fs" % (OUT, time.time() - t0))


if __name__ == "__main__":
    main()
