#!/usr/bin/env python3
"""Print full latest week section from dair-ai 2026.md, offset-aware."""
import json, base64, urllib.request, re, sys

def fetch(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"Accept": "application/vnd.github+json", "User-Agent": "hermes-cron"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    d = fetch("https://api.github.com/repos/dair-ai/AI-Papers-of-the-Week/contents/years/2026.md")
    txt = base64.b64decode(d["content"]).decode("utf-8", "ignore")
    heads = re.findall(r'^## (.+)$', txt, re.M)
    first = heads[0]
    idx = txt.find(first)
    end = txt.find("\n## ", idx + 10)
    section = txt[idx:end if end > 0 else idx + 40000]
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    print(section[start:start+12000])

if __name__ == "__main__":
    main()
