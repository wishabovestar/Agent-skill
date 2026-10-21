# -*- coding: utf-8 -*-
"""巡天知识采集更新 2026-10-20 —— 强制直连 + 去重 + 落盘"""
import ssl, sys, io, json, os, time, re, urllib.request, urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                     urllib.request.HTTPSHandler(context=CTX))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

TOK = None
for p in ['D:/hermes/data/credentials/github_token.txt', 'D:/hermes/data/credentials/github.json']:
    if os.path.exists(p):
        try:
            t = open(p, encoding='utf-8').read().strip()
            TOK = json.loads(t).get('token') if t.startswith('{') else t
            break
        except Exception:
            pass
print("TOKEN_LOADED=", bool(TOK))

def get(url, timeout=30, tries=3):
    for i in range(tries):
        try:
            h = {"User-Agent": UA, "Accept": "application/json,application/atom+xml,text/html,*/*"}
            if TOK and "api.github.com" in url:
                h["Authorization"] = "Bearer " + TOK
            with OPENER.open(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                print("  ERR", url[:70], type(e).__name__, str(e)[:80])
            time.sleep(3)
    return None

# ---------- 1. seen 集合（近 45 天归档，递归收集 full_name） ----------
ROOT = Path("D:/hermes/data/agent_knowledge")
seen = set()
cutoff = time.time() - 45 * 86400
files = 0
def walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("full_name", "repo", "name") and isinstance(v, str) and "/" in v:
                seen.add(v.lower())
            else:
                walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)
for fp in ROOT.rglob("*.json"):
    try:
        if fp.stat().st_mtime < cutoff:
            continue
        walk(json.loads(fp.read_text(encoding="utf-8", errors="ignore")))
        files += 1
    except Exception:
        pass
print(f"SEEN_FILES={files} SEEN_REPOS={len(seen)}")

# ---------- 2. GitHub 搜索 ----------
since7 = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
since14 = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
since30 = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
QUERIES = [
    ("agent",   f"topic:agent created:>{since14} stars:>80"),
    ("agent",   f"topic:mcp created:>{since14} stars:>50"),
    ("agent",   f"topic:claude-code created:>{since30} stars:>100"),
    ("agent",   f"agent+harness created:>{since14} stars:>30"),
    ("algo",    f"topic:llm-training created:>{since30} stars:>50"),
    ("algo",    f"topic:diffusion-models created:>{since30} stars:>80"),
    ("algo",    f"topic:reinforcement-learning created:>{since14} stars:>40"),
    ("hot",     f"created:>{since7} stars:>200"),
]
JUNK = re.compile(r"react-|sortable|tablesorter|revogrid|data-grid|jquery|plugin-|cheat|respocket|"
                  r"jailbreak|bitwarden|ps5|cs2-|save-editor|emulator|course|interview", re.I)

repos, qlog = [], []
for tag, q in QUERIES:
    url = ("https://api.github.com/search/repositories?q=" + urllib.parse.quote(q, safe=":+><")
           + "&sort=stars&order=desc&per_page=12")
    raw = get(url)
    n = 0
    if raw:
        try:
            d = json.loads(raw.decode("utf-8", "ignore"))
            items = d.get("items") or []
            total = d.get("total_count")
            for it in items:
                fn = it.get("full_name", "")
                if not fn or JUNK.search(fn) or JUNK.search(it.get("description") or ""):
                    continue
                if not (it.get("description") or "").strip():
                    continue
                dup = fn.lower() in seen
                repos.append({"full_name": fn, "stars": it.get("stargazers_count"),
                              "created": (it.get("created_at") or "")[:10],
                              "lang": it.get("language"), "pushed": (it.get("pushed_at") or "")[:10],
                              "desc": (it.get("description") or "").strip()[:200],
                              "url": it.get("html_url"), "topic": tag, "dup": dup})
                n += 1
            qlog.append((tag, q, total, len(items), n))
        except Exception as e:
            qlog.append((tag, q, "parse_err", str(e)[:40], 0))
    print(f"[{tag}] {q[:52]} -> kept={n}")
    time.sleep(7)

newr = [r for r in repos if not r["dup"]]
dupr = [r for r in repos if r["dup"]]

# ---------- 3. arXiv 新论文 ----------
AX = [
    ("llm-agent", 'abs:"agent" AND abs:"tool"'),
    ("agent-memory", 'abs:"memory" AND abs:"agent"'),
    ("harness-eval", 'abs:"harness" AND abs:"agent"'),
    ("rl-llm", 'abs:"reinforcement learning" AND abs:"language model"'),
    ("solid-state-battery", 'abs:"solid-state electrolyte"'),
    ("battery-manufacturing", 'abs:"electrode" AND abs:"manufacturing"'),
]
papers = []
for tag, q in AX:
    url = ("http://export.arxiv.org/api/query?search_query=" + urllib.parse.quote(q, safe="")
           + "&max_results=8&sortBy=submittedDate&sortOrder=descending")
    raw = get(url)
    if not raw:
        print(f"[ax:{tag}] FAIL")
        continue
    txt = raw.decode("utf-8", "ignore")
    ents = re.findall(r"<entry>(.*?)</entry>", txt, re.S)
    n = 0
    for e in ents:
        def pick(p, s=1):
            m = re.search(p, e, re.S)
            return re.sub(r"\s+", " ", m.group(s)).strip() if m else ""
        aid = pick(r"<id>(.*?)</id>").replace("http://arxiv.org/abs/", "")
        papers.append({"id": aid, "title": pick(r"<title>(.*?)</title>"),
                       "date": pick(r"<published>(.*?)</published>")[:10],
                       "authors": re.findall(r"<name>(.*?)</name>", e)[:3],
                       "summary": pick(r"<summary>(.*?)</summary>")[:600], "topic": tag})
        n += 1
    print(f"[ax:{tag}] got={n}")
    time.sleep(3)

# ---------- 4. 落盘 ----------
OUT = Path("D:/hermes/analysis")
stamp = datetime.now().strftime("%Y%m%d_%H%M")
payload = {"run_at": datetime.now().isoformat(timespec="seconds"),
           "queries": [{"tag": a, "q": b, "total": c, "returned": d, "kept": e} for a, b, c, d, e in qlog],
           "repos_new": newr, "repos_dup": dupr, "papers": papers,
           "seen_repos": len(seen), "seen_files": files}
(OUT / f"_xt_update_{stamp}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"SAVED _xt_update_{stamp}.json  new={len(newr)} dup={len(dupr)} papers={len(papers)}")
