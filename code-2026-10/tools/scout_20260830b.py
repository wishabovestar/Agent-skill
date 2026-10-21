# -*- coding: utf-8 -*-
"""巡天GitHub侦察 2026-08-30 第二轮 — 补充算法查询 + 高价值项目详情"""
import ssl, urllib.request, urllib.parse, json, time, os

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
    qq = urllib.parse.quote(q, safe=":+>")
    url = f"https://api.github.com/search/repositories?q={qq}&sort=stars&order=desc&per_page={per_page}"
    for attempt in range(3):
        try:
            d = gh_get(url)
            return d.get("total_count", 0), (d.get("items") or [])
        except Exception as e:
            print(f"  [retry {attempt+1}] {q[:40]} -> {e}", flush=True)
            time.sleep(10)
    return 0, []

QUERIES2 = [
    ("dl_2026",   "deep learning created:>2026-01-01 stars:>800", 10),
    ("nn_2026",   "neural network created:>2026-01-01 stars:>800", 10),
    ("llm_week",  "LLM created:>2026-08-20 stars:>300", 10),
    ("agent_fw",  "agent framework created:>2026-01-01 stars:>1000", 10),
]

out2 = {}
for tag, q, pp in QUERIES2:
    print(f"[{tag}] {q}", flush=True)
    total, items = search(q, pp)
    print(f"  total={total} items={len(items)}", flush=True)
    out2[tag] = {"query": q, "total": total, "items": items}
    time.sleep(8)

# 高价值项目详情（repos API，无search限额）
DETAILS = [
    "farion1231/cc-switch", "iOfficeAI/AionUi", "sapientinc/PRAXIST",
    "XiaoDuoYa/codex-with-chatgpt", "deepseek-ai/DeepSpec", "Optima-CityU/LLM4AD_Next",
    "bytedance/deer-flow", "headroomlabs-ai/headroom", "tirth8205/code-review-graph",
    "DeusData/codebase-memory-mcp", "wide-trace/open-higgsfield", "Tencent/WeMM-Embedding",
    "Nanako0129/sepia", "coleam00/context-engineering-intro", "HKUDS/nanobot",
]
det = {}
for fn in DETAILS:
    d = repo_detail_safe(fn) if False else None
    try:
        d = gh_get(f"https://api.github.com/repos/{fn}")
        det[fn] = {
            "stars": d.get("stargazers_count"),
            "created": d.get("created_at"),
            "pushed": d.get("pushed_at"),
            "license": (d.get("license") or {}).get("spdx_id"),
            "topics": d.get("topics"),
            "desc": d.get("description"),
            "html_url": d.get("html_url"),
        }
        print(f"[detail] {fn} stars={det[fn]['stars']} pushed={det[fn]['pushed'][:10]} topics={det[fn]['topics']}", flush=True)
    except Exception as e:
        print(f"  [detail fail] {fn}: {e}", flush=True)
    time.sleep(2)

with open("D:/hermes/data/agent_knowledge/算法/scout_raw2_20260830.json", "w", encoding="utf-8") as f:
    json.dump({"queries": out2, "details": det}, f, ensure_ascii=False, indent=1)
print("\nDONE2")
