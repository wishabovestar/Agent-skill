#!/usr/bin/env python3
"""Fetch paper digest READMEs from GitHub."""
import json, base64, urllib.request, datetime

def fetch(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"Accept": "application/vnd.github+json", "User-Agent": "hermes-cron"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))

def get_readme(repo):
    try:
        d = fetch(f"https://api.github.com/repos/{repo}/readme")
        return base64.b64decode(d["content"]).decode("utf-8", "ignore")
    except Exception as e:
        return f"[ERR {repo}: {e}]"

def search_repos(q, sort="updated", per=8):
    try:
        d = fetch(f"https://api.github.com/search/repositories?q={urllib.parse.quote(q)}&sort={sort}&order=desc&per_page={per}")
        return d.get("items", [])
    except Exception as e:
        print("  search err:", e)
        return []

if __name__ == "__main__":
    import urllib.parse
    r1 = get_readme("dair-ai/AI-Papers-of-the-Week")
    print("=== dair-ai/AI-Papers-of-the-Week README (first 5000) ===")
    print(r1[:5000])
    print("\n\n=== battery paper repos pushed recently ===")
    for r in search_repos("lithium battery OR solid-state battery arxiv papers", per=8):
        print(f"{r['full_name']} | pushed {r['pushed_at'][:10]} | {(r.get('description') or '')[:90]}")
    print("\n=== solid state battery repos ===")
    for r in search_repos("solid state battery 2026", per=6):
        print(f"{r['full_name']} | pushed {r['pushed_at'][:10]} | {(r.get('description') or '')[:90]}")
