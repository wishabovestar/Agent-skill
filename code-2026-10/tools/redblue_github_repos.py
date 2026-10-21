# -*- coding: utf-8 -*-
"""直接repo查询: 知名加密审计工具 (避免search限额)"""
import ssl, urllib.request, json, time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) hermes-scout",
      "Accept": "application/vnd.github+json"}

REPOS = [
    "drwetter/testssl.sh", "guidovranken/cryptofuzz", "RUB-NDS/TLS-Attacker",
    "trailofbits/semgrep-rules", "PyCQA/bandit", "securego/gosec",
    "projectdiscovery/nuclei", "zmap/zgrab2", "danielmiessler/SecLists",
]

def gh_repo(name):
    url = f"https://api.github.com/repos/{name}"
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
            return f"{d['full_name']}|stars={d['stargazers_count']}|updated={d.get('pushed_at','')[:10]}|{(d.get('description') or 'N/A')[:140]}"
    except Exception as e:
        return f"{name}|ERROR: {e}"

for r in REPOS:
    print(gh_repo(r))
    time.sleep(2)
print("DONE")
