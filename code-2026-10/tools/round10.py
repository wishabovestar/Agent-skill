#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第十轮：GitHub trending 多镜像 + 病毒学详情 + 澎湃 DeepSeek"""
import subprocess, re, html, time, json

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

def strip_tags(s):
    s = re.sub(r'<script.*?</script>', ' ', s, flags=re.S)
    s = re.sub(r'<style.*?</style>', ' ', s, flags=re.S)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = html.unescape(s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

if __name__ == "__main__":
    # GitHub trending 更多镜像
    print("########## GitHub trending 镜像扫描 ##########")
    urls = [
        "https://api.github.com/search/repositories?q=stars:%3E1000&sort=updated&order=desc&per_page=5",
        "https://gh.api.99988866.xyz/https://github.com/trending",
        "https://gitclone.com/github.com/trending",
        "https://github.com.cnpmjs.org/trending",
        "https://hub.yzuu.cf/trending",
        "https://hub.njuu.cf/trending",
    ]
    for u in urls:
        data = fetch(u)
        if data.startswith("ERR") or not data.strip():
            print(f"== {u}: EMPTY/ERR")
            continue
        try:
            j = json.loads(data)
            if isinstance(j, dict) and 'items' in j:
                print(f"== {u}: JSON items={len(j['items'])}")
                for r in j['items'][:5]:
                    print(f"   {r['full_name']} ★{r['stargazers_count']} | {(r.get('description') or '')[:80]}")
        except Exception:
            txt = strip_tags(data)
            print(f"== {u}: len={len(txt)}")
            print(txt[:500])
        time.sleep(0.8)

    # 病毒学详情
    print("\n########## 病毒学详情 ##########")
    for u in [
        "https://www.nyp.org/healthmatters/what-to-know-about-the-new-covid-variant-ba-32-cicada",
        "https://www.cdc.gov/fluview/index.html",
    ]:
        data = fetch(u)
        txt = strip_tags(data)
        print(f"\n== {u}: len={len(txt)}")
        print(txt[:1000])
        time.sleep(0.8)
