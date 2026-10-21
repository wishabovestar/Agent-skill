#!/usr/bin/env python3
"""GitHub trending + repo search helper."""
import json, sys, urllib.request, datetime

def fetch(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"Accept": "application/vnd.github+json", "User-Agent": "hermes-cron"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if mode == "daily":
        # GitHub trending approximation: repos created recently with most stars
        since = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        url = f"https://api.github.com/search/repositories?q=created:>{since}&sort=stars&order=desc&per_page=15"
        d = fetch(url)
        print("=== RECENT REPOS (created last 7d, by stars) ===")
        for r in d.get("items", []):
            print(f"{r['full_name']} | stars:{r['stargazers_count']} | {r.get('language')} | {(r.get('description') or '')[:100]}")
        print()
        # Popular repos updated recently (trending proxy: high star velocity)
        url2 = "https://api.github.com/search/repositories?q=pushed:>%s&sort=stars&order=desc&per_page=15" % (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
        d2 = fetch(url2)
        print("=== TOP STARRED UPDATED RECENTLY ===")
        for r in d2.get("items", []):
            print(f"{r['full_name']} | stars:{r['stargazers_count']} | {(r.get('description') or '')[:100]}")
    elif mode == "ai":
        url = "https://api.github.com/search/repositories?q=ai+OR+llm+OR+agent+pushed:>%s&sort=stars&order=desc&per_page=10" % (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        d = fetch(url)
        print("=== AI/LLM/AGENT REPOS (pushed last 7d) ===")
        for r in d.get("items", []):
            print(f"{r['full_name']} | stars:{r['stargazers_count']} | {(r.get('description') or '')[:100]}")

if __name__ == "__main__":
    main()
