# -*- coding: utf-8 -*-
"""补充查询: 防御侧加密审计工具 + 2025-2026 CVE"""
import ssl, urllib.request, urllib.parse, json, time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) hermes-scout",
      "Accept": "application/vnd.github+json"}

QUERIES = [
    ("defense", "testssl TLS scanner stars:>300"),
    ("defense", "cryptography misuse static analysis bandit semgrep"),
    ("defense", "JWT security scanner stars:>100"),
    ("attack", "CVE-2025 crypto vulnerability"),
    ("defense", "hashing password audit weak algorithm stars:>100"),
]

def gh_search(q, per_page=6):
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
        {"q": q, "sort": "stars", "order": "desc", "per_page": per_page})
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        return {"error": str(e)}

for side, q in QUERIES:
    data = gh_search(q)
    print(f"=== [{side}] {q} ===")
    if "error" in data:
        print("  ERROR:", data["error"])
        time.sleep(8)
        continue
    items = data.get("items") or []
    for i in items[:5]:
        desc = (i.get("description") or "N/A")[:150]
        print(f"  {i['full_name']}|stars={i['stargazers_count']}|{desc}")
    time.sleep(8)

print("DONE")
