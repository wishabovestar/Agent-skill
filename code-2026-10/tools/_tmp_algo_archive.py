# -*- coding: utf-8 -*-
"""归档：写入 algorithm/<方向>/<date>.json + 更新 algorithm_log.json"""
import json, os, datetime, collections

BASE = r"D:/hermes/data/agent_knowledge"
OUT = os.path.join(BASE, "algorithm")
RAW = os.path.join(OUT, "tmp")
TODAY = datetime.date.today().isoformat()

seen = json.load(open(os.path.join(RAW, "seen.json"), encoding="utf-8"))
sr = set(x.lower() for x in seen["repos"])
sp = set(seen["papers"])

gh = json.load(open(os.path.join(RAW, "github_raw.json"), encoding="utf-8"))
gh2 = json.load(open(os.path.join(RAW, "github_raw2.json"), encoding="utf-8"))
for x in gh2:
    x.setdefault("is_new", x["full_name"].lower() not in sr)
ax = json.load(open(os.path.join(RAW, "arxiv_raw.json"), encoding="utf-8"))
tr = json.load(open(os.path.join(RAW, "arxiv_trends.json"), encoding="utf-8"))

DIRMAP = {  # 英文方向(可多对一) -> 中文目录
    "algorithm": ("算法原理",),
    "math": ("数学原理",),
    "system": ("计算机原理",),
    "dl": ("深度学习",),
    "ml": ("机器学习",),
    "neural": ("神经算法CNN_LLM",),
    "hotspot": ("热点项目",),
    "agent": ("热点项目",),
}
# 趋势主题归类
TREND_MAP = {
    "kv_cache": "neural", "spec_decoding": "neural", "sparse_attn": "neural",
    "moe": "neural", "quantization": "neural",
    "token_compress": "dl", "test_time": "dl", "agent_memory": "neural",
}
for x in gh + gh2:
    x.setdefault("is_new", x["full_name"].lower() not in sr)

summary = {}
all_trends = []
CN2EN = collections.OrderedDict()
for en, (cn,) in DIRMAP.items():
    CN2EN.setdefault(cn, []).append(en)
for cn, ens in CN2EN.items():
    repos_all = {}
    for x in [y for y in gh + gh2 if y["direction"] in ens]:
        repos_all[x["full_name"]] = x
    ranked = sorted(repos_all.values(), key=lambda z: -z["stars"])
    repos = ranked[:10]
    extra_new = [r for r in ranked[10:] if r.get("is_new")][:10]
    repos = repos + extra_new
    new_repos = [r for r in repos if r.get("is_new")]
    pap = {}
    for en in ens:
        for p in ax.get(en, []):
            pid = p["id"].rstrip("/").split("/")[-1]
            p["is_new"] = pid not in sp
            pap[p["id"]] = p
    # 趋势论文并入
    for topic, tgt in TREND_MAP.items():
        if tgt in ens:
            for p in tr.get(topic, []):
                if "err" in p: continue
                p = dict(p); p["topic"] = topic
                pap.setdefault(p["id"], p)
    papers = list(pap.values())[:60]
    new_papers = [p for p in papers if p.get("is_new", True)]
    doc = {
        "date": TODAY, "direction": cn, "repos": repos, "new_repos": new_repos,
        "papers": papers, "new_papers": new_papers, "arxiv_via_proxy": False,
    }
    os.makedirs(os.path.join(OUT, cn), exist_ok=True)
    fp = os.path.join(OUT, cn, TODAY + ".json")
    json.dump(doc, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    summary[cn] = {"repos": len(repos), "new_repos": len(new_repos),
                   "papers": len(papers), "new_papers": len(new_papers)}

# 趋势文件
tf = os.path.join(OUT, "神经算法CNN_LLM", "trends_%s.json" % TODAY)
json.dump({"date": TODAY, "topics": tr}, open(tf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# 更新总日志
lgp = os.path.join(BASE, "algorithm_log.json")
lg = json.load(open(lgp, encoding="utf-8"))
tot_repos = sum(1 for x in gh + gh2 if not x.get("archived"))
tot_papers = sum(len(v) for v in ax.values()) + sum(len([p for p in v if "err" not in p]) for v in tr.values())
entry = {
    "date": TODAY + "T06:00:00",
    "source": "xuntian-github-scout-algorithm-extension",
    "targets": ["github/algorithm", "github/math", "github/os-compiler", "github/deep-learning",
                "github/machine-learning", "github/neural-cnn-llm",
                "arxiv/cs.DS", "arxiv/math.NA", "arxiv/math.OC", "arxiv/math.ST",
                "arxiv/cs.AR", "arxiv/cs.PL", "arxiv/cs.DC", "arxiv/cs.LG", "arxiv/stat.ML",
                "arxiv/cs.CL", "arxiv/cs.CV", "arxiv/cs.NE",
                "arxiv/trends/kv-cache,spec-decoding,moe,sparse-attn,test-time,quantization,token-compression,agent-memory"],
    "github_repos_total": tot_repos,
    "arxiv_papers_total": tot_papers,
    "directions": summary,
    "trend_signals": [
        "KV缓存淘汰转向Agent感知：AgentKV按推理阶段差异化淘汰KV，RAG场景REVA复用证据视图",
        "投机解码进入自投机+异步批处理：ASPIRE/LoopSpec/ECHO三条路线，长上下文为主要战场",
        "上下文压缩模型统一化：FlexComp单模型覆盖任意压缩比；Attribution-Compression Frontier给出RAG权衡理论边界",
        "MoE重用专家：MoRE（Mixture of Reused Experts）降低专家调度与参数搬运开销",
        "推理优化评测标准化：Inference Engineering Pareto Atlas + 校准化质量影响仪器，让优化可量化对比",
        "1-bit/极端量化推进：All for 1-Bit 真正1-bit PTQ；Vortex 桥接极端压缩与推理效率",
        "测试时算力重新审视：'Intelligence Under Time Constraints' 质疑无脑加算力，Elo-per-token 度量Agent测试时策略",
    ],
    "deep_read": [
        "AgentKV: Phase-Aware KV Eviction for Agentic LLMs (arXiv 2026-09-14) — 直接对应Hermes会话历史压缩",
        "The Inference Engineering Pareto Atlas (arXiv 2026-09-15) — 成本/质量/延迟取舍总览，可指导Hermes本地模型选型",
        "DeepSeek-V4-Flash on AMD gfx90a: Correctness Recovery and Inference Performance Engineering (2026-09-14) — 本集群主力模型推理工程",
        "bojieli/ai-infra-book (GitHub 4122⭐) — 《深入理解AI Infra：量化分析与系统设计》开源书",
    ],
    "note": "arXiv 本地直连可用(无需VPS中转)；GitHub search API 未认证限速，14查询/轮已用sleep 8s规避",
}
lg["collections"] = [c for c in lg.get("collections", [])
                     if not (c.get("date", "")[:10] == TODAY and c.get("source") == entry["source"])] + [entry]
lg["last_collection"] = TODAY
json.dump(lg, open(lgp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("ARCHIVE_DONE", json.dumps(summary, ensure_ascii=False))
print("TOTAL repos=%d papers=%d log_entries=%d" % (tot_repos, tot_papers, len(lg["collections"])))
