#!/usr/bin/env python3
"""Fetch battery paper repo readme + search more battery repos."""
import json, base64, urllib.request, urllib.parse

def fetch(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"Accept": "application/vnd.github+json", "User-Agent": "hermes-cron"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))

def get_readme(repo):
    try:
        d = fetch(f"https://api.github.com/repos/{repo}/readme")
        return base64.b64decode(d["content"]).decode("utf-8", "ignore")
    except Exception as e:
        return f"[ERR: {e}]"

if __name__ == "__main__":
    r = get_readme("flwang1998/NatComm-2026-Polyanion-stabilized-amorphous-halide-electrolytes")
    print("=== NatComm halide electrolyte repo README ===")
    print(r[:2500])
    print("\n=== battery repos pushed recently ===")
    for q in ["solid-state battery", "lithium battery materials 2026", "electrolyte battery paper"]:
        try:
            d = fetch(f"https://api.github.com/search/repositories?q={urllib.parse.quote(q)}&sort=updated&order=desc&per_page=5")
            print(f"--- {q} ---")
            for it in d.get("items", []):
                print(f"{it['full_name']} | pushed {it['pushed_at'][:10]} | {(it.get('description') or '')[:80]}")
        except Exception as e:
            print("  err:", e)
