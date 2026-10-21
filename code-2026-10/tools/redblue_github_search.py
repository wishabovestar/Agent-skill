# -*- coding: utf-8 -*-
"""巡天加密审计主题 GitHub 检索脚本 (cron-safe: 无内联危险命令)"""
import ssl, urllib.request, urllib.parse, json, time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) hermes-scout",
      "Accept": "application/vnd.github+json"}

QUERIES = [
    # 攻击侧: 加密弱点利用
    ("attack", "weak cryptography vulnerability exploit stars:>50"),
    ("attack", "JWT algorithm confusion attack"),
    ("attack", "padding oracle attack tool"),
    ("attack", "crypto audit vulnerable implementation"),
    # 防御侧: 加密审计/检测
    ("defense", "TLS audit scanner stars:>200"),
    ("defense", "crypto agility weak algorithm detection"),
    ("defense", "cryptography linter misuse detection stars:>100"),
    ("defense", "hashcat weak hash NTLM cracking detection"),
]

def gh_search(q, per_page=8):
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
    for i in items[:6]:
        desc = (i.get("description") or "N/A")[:160]
        print(f"  {i['full_name']}|stars={i['stargazers_count']}|lang={i.get('language')}|{desc}")
    time.sleep(8)  # GitHub search API 未认证限额 10次/min

print("DONE")
