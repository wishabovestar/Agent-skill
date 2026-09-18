#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_wired_types.py — 实测 4 个"有风险"的接线文件是否真能取到数

★ 背景(r1192): 我 r1186 的 `cg.run` drop-in 把 stdout 从 bytes 变成 str,
  导致调用方 `r.stdout.decode()` 抛 AttributeError, 而多处用 `except: continue` 包裹
  ⇒ ★ 静默失效(collect_hf 的 fetch 恒返回 None)。

★ 本脚本【不 in-process import 被测脚本】(r1186 教训: 部分脚本在模块顶层执行业务)。
  改为 subprocess 隔离: 每个文件单独起进程, 直接测"取数 + .decode()"这条路径。
"""
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = r"D:\hermes\hermes-data\profiles\qqbot3"
PY = sys.executable
SCRIPTS = os.path.join(BASE, "scripts")

# (相对路径, 一个真实 URL, 说明)
CASES = [
    (r"scripts\rss_cache.py", "https://rsshub.app/github/trending/daily/any", "RSS 缓存"),
    (r"scripts\xuntian_anthropic_blog.py", "https://www.anthropic.com/news", "Anthropic 博客"),
    (r"scripts\xuntian_github_trending.py", "https://github.com/trending", "GitHub Trending"),
    (r"scripts\xuntian_neo4j_blog.py", "https://neo4j.com/blog/", "Neo4j 博客"),
]

CODE = r'''
import sys
sys.path.insert(0, r"{scripts}")
sys.path.insert(0, r"{base}")
import curl_guarded as cg
u = {url!r}
# 复刻这些脚本的调用形态: capture_output 但【不传 text=True】⇒ 期望 bytes
r = cg.run(["curl", "-skL", "--max-time", "30", "-A", "Mozilla/5.0", u],
           capture_output=True, timeout=45)
t = type(r.stdout).__name__
n = 0
try:
    if r.returncode == 0 and r.stdout and r.stdout.strip():
        s = r.stdout.decode("utf-8", "replace")     # ★ 这就是会炸的那行
        n = len(s)
    print("OK" if n > 200 else "SHORT", "rtype=%s" % t, "rc=%d" % r.returncode, "len=%d" % n)
except Exception as e:
    print("FAIL", "%s: %s" % (type(e).__name__, str(e)[:60]))
'''


def run_case(rel, url, note):
    code = CODE.format(scripts=SCRIPTS, base=BASE, url=url)
    try:
        p = subprocess.run([PY, "-X", "utf8", "-c", code],
                           capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return note, rel, "TIMEOUT", ""
    out = (p.stdout or "").strip().split("\n")[-1] if p.stdout else ""
    err = (p.stderr or "").strip()[-90:] if p.stderr else ""
    return note, rel, out or ("ERR " + err[:70]), err


print("=" * 84)
print("  实测: cg.run 类型修复后, 4 个'有 .decode() 风险'的接线文件")
print("=" * 84)
okc = 0
for rel, url, note in CASES:
    note, rel, res, err = run_case(rel, url, note)
    good = res.startswith("OK")
    okc += 1 if good else 0
    print("  %-18s %-52s %s" % (note, res[:52], "✅" if good else "🟡"))

print()
print("  ★ 成功 %d / %d" % (okc, len(CASES)))
print("  ★ 注: 🟡 可能是该站点本身不可达(非类型问题); 判据看 rtype 是否为 bytes 且无 FAIL")
