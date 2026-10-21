#!/usr/bin/env python3
"""Fetch recent ML paper digests from GitHub (dair-ai/ML-Papers-of-the-Week)."""
import json, base64, urllib.request, datetime

def fetch(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"Accept": "application/vnd.github+json", "User-Agent": "hermes-cron"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    # 1) recent commits to ML-Papers-of-the-Week
    try:
        commits = fetch("https://api.github.com/repos/dair-ai/ML-Papers-of-the-Week/commits?per_page=5")
        print("=== ML-Papers-of-the-Week recent commits ===")
        for c in commits:
            print(c["commit"]["author"]["date"][:10], "|", c["commit"]["message"][:80])
            print("   ", c["html_url"])
    except Exception as e:
        print("commits err:", e)

    # 2) repo contents top-level
    try:
        contents = fetch("https://api.github.com/repos/dair-ai/ML-Papers-of-the-Week/contents/")
        print("\n=== top-level files ===")
        for f in contents:
            print(f["name"], f.get("type"))
    except Exception as e:
        print("contents err:", e)

    # 3) check Papers-with-code / papers repos pushed recently
    try:
        since = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
        d = fetch("https://api.github.com/search/repositories?q=arxiv+papers+pushed:>%s&sort=updated&order=desc&per_page=8" % since)
        print("\n=== arxiv/papers repos pushed last 14d ===")
        for r in d.get("items", []):
            print(f"{r['full_name']} | pushed {r['pushed_at'][:10]} | {(r.get('description') or '')[:90]}")
    except Exception as e:
        print("search err:", e)

if __name__ == "__main__":
    main()
