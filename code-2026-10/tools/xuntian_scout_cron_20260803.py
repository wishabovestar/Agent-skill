# -*- coding: utf-8 -*-
"""巡天GitHub侦察 cron — 2026-08-03
策略: GitHub API curl直连(-k绕Schannel) → 热点+关键词+算法专项 → 相关性评分 → 前10报告
"""
import json, subprocess, time, os, datetime
from urllib.parse import quote

OUT_BASE = "D:/hermes/data/agent_knowledge"
ALGO_DIR = os.path.join(OUT_BASE, "算法")
SCOUT_DIR = os.path.join(OUT_BASE, "github_scout")
os.makedirs(ALGO_DIR, exist_ok=True)
os.makedirs(SCOUT_DIR, exist_ok=True)

def gh(url):
    """curl -s -k 直连GitHub API"""
    cmd = ["curl", "-s", "-k", "--max-time", "25", url]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None

def gh_search(q, per_page=10):
    url = f"https://api.github.com/search/repositories?q={quote(q, safe='+')}&sort=stars&order=desc&per_page={per_page}"
    d = gh(url)
    if not d:
        return []
    items = d.get("items") or []
    if "message" in d and not items:
        print(f"  [API警告] {d['message']}", flush=True)
    return items

def gh_repo(full_name):
    d = gh(f"https://api.github.com/repos/{full_name}")
    return d if isinstance(d, dict) and "id" in d else {}

today = datetime.date(2026, 8, 3)
week_ago = (today - datetime.timedelta(days=7)).isoformat()
two_week = (today - datetime.timedelta(days=14)).isoformat()

QUERIES = [
    ("hot_week",   f"created:>{week_ago} stars:>2000", "本周热点(7天)"),
    ("hot_2week",  f"created:>{two_week} stars:>500",  "两周潜力(14天)"),
    ("ai_agent",   "ai agent tool stars:>1000",        "AI Agent工具链"),
    ("mcp_server", "mcp server stars:>300",            "MCP生态"),
    ("code_assistant", "code assistant stars:>2000",   "编码助手"),
    ("search_engine", "search engine stars:>1000",     "搜索引擎"),
    ("cli_tool",   "cli tool stars:>2000",             "CLI工具链"),
]

ALGO_QUERIES = [
    ("algo_dl",   "deep learning created:>2026-01-01 stars:>2000", "深度学习"),
    ("algo_nn",   "neural network created:>2026-01-01 stars:>1500", "神经网络"),
    ("algo_alg",  "algorithm created:>2026-01-01 stars:>1500",     "算法"),
    ("algo_rl",   "reinforcement learning created:>2026-01-01 stars:>1000", "强化学习"),
]

def relevance_score(repo):
    name = (repo.get("full_name") or "").lower()
    desc = (repo.get("description") or "").lower()
    topics = " ".join((repo.get("topics") or [])).lower()
    text = f"{name} {desc} {topics}"
    score = 0.0
    strong = ["agent", "mcp", "llm", "ai assistant", "code assistant", "tool use",
              "copilot", "claude", "gpt", "rag", "autonomous", "coding agent"]
    medium = ["cli", "terminal", "command line", "search", "deep learning",
              "neural", "framework", "langchain"]
    weak = ["database", "api", "python", "algorithm", "inference", "open source"]
    for k in strong:
        if k in text: score += 3
    for k in medium:
        if k in text: score += 1.5
    for k in weak:
        if k in text: score += 0.5
    stars = repo.get("stargazers_count") or 0
    score += min(stars / 5000.0, 3.0)
    pushed = repo.get("pushed_at") or ""
    if pushed >= "2026-06-01": score += 1
    return round(score, 1)

def make_reason(repo, cat):
    desc = (repo.get("description") or "无描述")
    topics = repo.get("topics") or []
    tstr = ",".join(topics[:5]) if topics else "N/A"
    stars = repo.get("stargazers_count") or 0
    pushed = (repo.get("pushed_at") or "")[:10]
    reasons = []
    if any(k in (repo.get("full_name") or "").lower() + " " + desc.lower() for k in
           ["agent", "mcp", "coding", "assistant", "copilot"]):
        reasons.append("直接相关AI Agent/Hermes工具链")
    if any(k in desc.lower() for k in ["search", "retrieval", "rag"]):
        reasons.append("检索/知识增强方向")
    if cat.startswith("algo"):
        reasons.append("算法/AI专项候选")
    if pushed >= "2026-06-01":
        reasons.append(f"近期活跃({pushed})")
    if stars >= 5000:
        reasons.append("高星验证")
    reason = "; ".join(reasons) if reasons else "生态相关候选"
    return reason

# ========== 执行搜索 ==========
results = {}
for key, q, label in QUERIES + ALGO_QUERIES:
    print(f"[{label}] {q}", flush=True)
    items = gh_search(q)
    results[key] = items
    for it in items[:5]:
        print(f"   {it['full_name']} ⭐{it['stargazers_count']} | {(it.get('description') or '')[:80]}", flush=True)
    time.sleep(0.5)

# ========== 合并去重 + 评分 ==========
merged = {}
for key, q, label in QUERIES + ALGO_QUERIES:
    for it in results.get(key, []):
        fn = it.get("full_name")
        if not fn:
            continue
        if fn not in merged:
            it["_cats"] = [key]
            merged[fn] = it
        else:
            merged[fn]["_cats"].append(key)

for fn, it in merged.items():
    it["_score"] = relevance_score(it)

# ========== 详情增强(top综合候选前6) ==========
ranked = sorted(merged.values(), key=lambda x: x["_score"], reverse=True)
for it in ranked[:6]:
    detail = gh_repo(it["full_name"])
    if detail:
        it["topics"] = detail.get("topics") or it.get("topics") or []
        it["pushed_at"] = detail.get("pushed_at") or it.get("pushed_at") or ""
        it["license"] = (detail.get("license") or {}).get("spdx_id") or "N/A"
        it["open_issues"] = detail.get("open_issues_count") or 0
        it["homepage"] = detail.get("homepage") or ""
        it["_score"] = relevance_score(it)
    time.sleep(0.4)

ranked = sorted(merged.values(), key=lambda x: x["_score"], reverse=True)

# ========== 输出前10 ==========
print("\n===== TOP 10 高价值项目 =====", flush=True)
top10 = []
for i, it in enumerate(ranked[:10], 1):
    entry = {
        "rank": i,
        "full_name": it["full_name"],
        "stars": it["stargazers_count"],
        "language": it.get("language") or "N/A",
        "description": (it.get("description") or "无描述")[:300],
        "score": it["_score"],
        "cats": it["_cats"],
        "topics": it.get("topics") or [],
        "pushed_at": (it.get("pushed_at") or "")[:10],
        "license": it.get("license", "N/A"),
        "url": it.get("html_url") or f"https://github.com/{it['full_name']}",
        "reason": make_reason(it, it["_cats"][0]),
    }
    top10.append(entry)
    print(f"{i}. {entry['full_name']} ⭐{entry['stars']} [{entry['language']}] score={entry['score']} | {entry['description'][:90]}", flush=True)

# ========== 保存 ==========
stamp = "20260803"
# 算法专项
algo_items = [it for it in merged.values() if any(c.startswith("algo") for c in it["_cats"])]
algo_items = sorted(algo_items, key=lambda x: x["_score"], reverse=True)
algo_payload = {
    "date": stamp, "source": "github_api", "queries": [q for _, q, _ in ALGO_QUERIES],
    "items": [{
        "full_name": it["full_name"], "stars": it["stargazers_count"],
        "language": it.get("language"), "description": (it.get("description") or "")[:500],
        "topics": it.get("topics") or [], "url": it.get("html_url") or f"https://github.com/{it['full_name']}",
        "pushed_at": (it.get("pushed_at") or "")[:10], "score": it["_score"],
    } for it in algo_items[:15]],
}
algo_path = os.path.join(ALGO_DIR, f"github_scout_{stamp}.json")
with open(algo_path, "w", encoding="utf-8") as f:
    json.dump(algo_payload, f, ensure_ascii=False, indent=2)
print(f"\n[已保存] 算法专项 -> {algo_path} ({len(algo_items)}条)", flush=True)

# 综合侦察
scout_payload = {
    "date": stamp, "source": "github_api", "top10": top10,
    "stats": {"total_unique": len(merged), "per_query": {k: len(v) for k, v in results.items()}},
}
scout_path = os.path.join(SCOUT_DIR, f"github_scout_{stamp}.json")
with open(scout_path, "w", encoding="utf-8") as f:
    json.dump(scout_payload, f, ensure_ascii=False, indent=2)
print(f"[已保存] 综合侦察 -> {scout_path}", flush=True)
print("\n===== DONE =====", flush=True)
