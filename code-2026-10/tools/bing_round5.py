#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第五轮：GitHub 镜像 + arXivDaily + 病毒学细节"""
import subprocess, re, html, time

def fetch(url, ua=None):
    try:
        r = subprocess.run(
            ["curl", "-sL", "--max-time", "30", "-A",
             ua or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
             "-H", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
             url],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40)
        return r.stdout
    except Exception as e:
        return f"ERR {e}"

def strip_html(data):
    data = re.sub(r'<script.*?</script>', ' ', data, flags=re.S)
    data = re.sub(r'<style.*?</style>', ' ', data, flags=re.S)
    data = re.sub(r'<[^>]+>', ' ', data)
    data = html.unescape(data)
    data = re.sub(r'[ \t]+', ' ', data)
    data = re.sub(r'\n\s*\n+', '\n', data)
    return data.strip()

if __name__ == "__main__":
    # GitHub 镜像
    mirrors = [
        ("ghproxy api", "https://ghproxy.com/https://api.github.com/search/repositories?q=created:%3E2026-08-05&sort=stars&order=desc&per_page=10"),
        ("ghfast api", "https://ghfast.top/https://api.github.com/search/repositories?q=created:%3E2026-08-05&sort=stars&order=desc&per_page=10"),
        ("gh-proxy api", "https://gh-proxy.com/https://api.github.com/search/repositories?q=created:%3E2026-08-05&sort=stars&order=desc&per_page=10"),
        ("github mirror trending", "https://hub.gitmirror.com/trending"),
        ("github.com.cnpmjs trending", "https://github.com.cnpmjs.org/trending"),
    ]
    for name, u in mirrors:
        data = fetch(u)
        if data.startswith("ERR"):
            print(f"\n== {name}: {data}")
            continue
        # 尝试解析JSON
        try:
            import json
            j = json.loads(data)
            print(f"\n== {name}: JSON OK, total={j.get('total_count')}")
            for r in j.get('items', [])[:10]:
                print(f"  {r['full_name']} ★{r['stargazers_count']} | {(r.get('description') or '')[:100]}")
        except Exception:
            txt = strip_html(data)
            print(f"\n== {name}: len={len(txt)}")
            print(txt[:700])
        time.sleep(1.0)

    # arXivDaily
    print("\n\n########## arXivDaily ##########")
    data = fetch("https://www.arxivdaily.com/")
    txt = strip_html(data)
    print(f"len={len(txt)}")
    print(txt[:1500])
