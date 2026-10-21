# -*- coding: utf-8 -*-
"""巡天补跑 — 算法/RL查询重试 + 热点详情"""
import json, subprocess, time, os
from urllib.parse import quote

ALGO_DIR = "D:/hermes/data/agent_knowledge/算法"

def gh(url):
    cmd = ["curl", "-s", "-k", "--max-time", "25", url]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None

def gh_search(q, per_page=8):
    url = f"https://api.github.com/search/repositories?q={quote(q, safe='+')}&sort=stars&order=desc&per_page={per_page}"
    d = gh(url)
    if not d:
        return []
    return d.get("items") or []

def gh_repo(fn):
    d = gh(f"https://api.github.com/repos/{fn}")
    return d if isinstance(d, dict) and "id" in d else {}

print("等待60秒恢复搜索配额...", flush=True)
time.sleep(60)

ALGO_QUERIES = [
    ("algo_dl",  "deep learning created:>2026-01-01 stars:>2000", "深度学习"),
    ("algo_nn",  "neural network created:>2026-01-01 stars:>1500", "神经网络"),
    ("algo_alg", "algorithm created:>2026-01-01 stars:>1500", "算法"),
    ("algo_rl",  "reinforcement learning created:>2026-01-01 stars:>1000", "强化学习"),
]

algo_items = {}
for key, q, label in ALGO_QUERIES:
    print(f"[{label}] 重试 {q}", flush=True)
    items = gh_search(q)
    for it in items[:8]:
        fn = it["full_name"]
        if fn not in algo_items:
            it["_cat"] = key
            algo_items[fn] = it
        print(f"   {fn} ⭐{it['stargazers_count']} | {(it.get('description') or '')[:80]}", flush=True)
    time.sleep(8)  # 搜索API 10req/min，间隔8s稳妥

# 热点详情补充
print("\n[热点详情] yc-software/qm + MoonshotAI/Kimi-K3", flush=True)
details = {}
for fn in ["yc-software/qm", "MoonshotAI/Kimi-K3", "bashalarmistalt/decimen-optical-transfer"]:
    d = gh_repo(fn)
    if d:
        details[fn] = {
            "full_name": fn, "stars": d.get("stargazers_count"),
            "desc": (d.get("description") or "")[:400],
            "topics": d.get("topics") or [], "pushed": (d.get("pushed_at") or "")[:10],
            "created": (d.get("created_at") or "")[:10],
            "license": (d.get("license") or {}).get("spdx_id") or "N/A",
            "forks": d.get("forks_count"), "open_issues": d.get("open_issues_count"),
        }
        print(f"   {fn}: created={details[fn]['created']} pushed={details[fn]['pushed']} topics={details[fn]['topics'][:4]}", flush=True)
    time.sleep(2)

# 合并保存算法专项
out = {
    "date": "20260803", "source": "github_api_retry",
    "queries": [q for _, q, _ in ALGO_QUERIES],
    "items": [{
        "full_name": it["full_name"], "stars": it["stargazers_count"],
        "language": it.get("language"), "description": (it.get("description") or "")[:500],
        "topics": it.get("topics") or [], "url": it.get("html_url") or f"https://github.com/{it['full_name']}",
        "pushed_at": (it.get("pushed_at") or "")[:10], "category": it["_cat"],
    } for it in sorted(algo_items.values(), key=lambda x: x["stargazers_count"], reverse=True)],
}
path = os.path.join(ALGO_DIR, "github_scout_20260803.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"\n[已保存] 算法专项(补全) -> {path} ({len(algo_items)}条)", flush=True)

dp = os.path.join(ALGO_DIR, "hotspot_details_20260803.json")
with open(dp, "w", encoding="utf-8") as f:
    json.dump(details, f, ensure_ascii=False, indent=2)
print(f"[已保存] 热点详情 -> {dp}", flush=True)
print("===== DONE =====", flush=True)
