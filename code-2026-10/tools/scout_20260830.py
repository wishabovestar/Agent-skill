# -*- coding: utf-8 -*-
"""巡天GitHub侦察 2026-08-30 — urllib直调GitHub API（规避Schannel问题）"""
import ssl, urllib.request, urllib.parse, json, time, os, sys

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HDRS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/vnd.github+json"}

def gh_get(url, timeout=25):
    req = urllib.request.Request(url, headers=HDRS)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.loads(r.read().decode("utf-8", errors="ignore"))

def search(q, per_page=10):
    """q: 原始查询字符串，用safe保留 + : > 字符"""
    qq = urllib.parse.quote(q, safe=":+>")
    url = f"https://api.github.com/search/repositories?q={qq}&sort=stars&order=desc&per_page={per_page}"
    for attempt in range(3):
        try:
            d = gh_get(url)
            items = d.get("items") or []
            return d.get("total_count", 0), items
        except Exception as e:
            print(f"  [retry {attempt+1}] {q[:40]} -> {e}", flush=True)
            time.sleep(10)
    return 0, []

def repo_detail(full_name):
    try:
        return gh_get(f"https://api.github.com/repos/{full_name}")
    except Exception as e:
        print(f"  [detail fail] {full_name}: {e}", flush=True)
        return None

QUERIES = [
    # ---- 本周热点（created > 2026-08-23）----
    ("weekly_hot",    "created:>2026-08-23 stars:>2000", 15),
    ("weekly_potential", "created:>2026-08-23 stars:>500", 15),
    # ---- AI Agent工具链关键词 ----
    ("ai_agent",      "ai agent tool stars:>2000", 10),
    ("mcp_server",    "mcp server stars:>500", 10),
    ("code_assistant","code assistant stars:>2000", 10),
    ("search_engine", "search engine stars:>1000", 10),
    ("cli_tool",      "cli tool stars:>2000", 10),
    # ---- 扩展：算法/深度学习/神经网络 ----
    ("dl_recent",     "deep learning created:>2026-06-01 stars:>500", 15),
    ("nn_recent",     "neural network created:>2026-06-01 stars:>500", 15),
    ("algo_recent",   "algorithm created:>2026-06-01 stars:>300", 15),
]

out = {}
for tag, q, pp in QUERIES:
    print(f"[{tag}] {q}", flush=True)
    total, items = search(q, pp)
    print(f"  total={total} items={len(items)}", flush=True)
    out[tag] = {"query": q, "total": total, "items": items}
    time.sleep(8)  # search API限额 10/min

os.makedirs("D:/hermes/data/agent_knowledge/算法", exist_ok=True)
with open("D:/hermes/data/agent_knowledge/算法/scout_raw_20260830.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

# 输出精简摘要
for tag, blk in out.items():
    print(f"\n===== {tag} (total={blk['total']}) =====")
    for i in blk["items"]:
        print(f"  {i['full_name']}|{i['stargazers_count']}|{i.get('language','N/A')}|{(i.get('description') or '')[:120]}")
print("\nDONE")
