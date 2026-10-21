# -*- coding: utf-8 -*-
"""GitHub 月度推送（no_agent cron）—— 每月 1 号 09:00 推微信。

口径：
  A 线「新建」：created:>=起始日 stars:>30，按星数取前 3/式
  B 线「活跃」：pushed:>=起始日 stars:>3000，按星数取前 6（库在长，不一定新）
去重：gh_monthly_seen.json 记已推 full_name，同一库 90 天内只推一次。
失败出声：任一式失败记 FAIL 并在正文自曝；全部失败 exit 3。
"""
import io
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

AK = "D:/hermes/data/agent_knowledge/algorithm"
SEEN = os.path.join(AK, "gh_monthly_seen.json")
OUT = os.path.join(AK, "gh_monthly_%s.json" % datetime.now().strftime("%Y-%m"))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                     urllib.request.HTTPSHandler(context=CTX))

# 通用榜单/面试/教程类大库：topic 命中但无技术增量，月度推送里剔除
BLOCK = {"freeCodeCamp/freeCodeCamp", "public-apis/public-apis",
         "EbookFoundation/free-programming-books", "kamranahmedse/developer-roadmap",
         "Snailclimb/JavaGuide", "gitleaks/gitleaks", "996icu/996.ICU"}

KW = [
    "llm inference",
    "quantization",
    "agent framework",
    "speculative decoding",
    "context engineering",
    "battery electrode",
]


def api(url, tries=3, timeout=30):
    """403/429 = 未认证 search 限速（10 次/分），等 25s 重试；其余错误直接返回。"""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/vnd.github+json",
            })
            with OPENER.open(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:160]
            except Exception:
                pass
            if e.code in (403, 429) and i < tries - 1:
                time.sleep(25)
                continue
            return {"__err": "HTTP%s" % e.code, "__msg": body}
        except Exception as e:
            if i == tries - 1:
                return {"__err": type(e).__name__}
            time.sleep(5)


def main():
    dry = "--dry-run" in sys.argv
    now = datetime.now()
    start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    stamp = now.strftime("%Y-%m")
    fails = []
    rows = []

    def add(items, line, limit):
        n = 0
        for it in items:
            if n >= limit:
                break
            full = it.get("full_name")
            if not full or full in BLOCK:
                continue
            rows.append({
                "full_name": full,
                "stars": it.get("stargazers_count") or 0,
                "desc": (it.get("description") or "").strip(),
                "lang": it.get("language") or "—",
                "created": (it.get("created_at") or "")[:10],
                "pushed": (it.get("pushed_at") or "")[:10],
                "url": it.get("html_url") or "",
                "line": line,
            })
            n += 1

    # A 线：本月新建
    for kw in KW:
        q = ("%s created:>=%s stars:>30" % (kw, start)).replace(" ", "+")
        d = api("https://api.github.com/search/repositories?q=%s"
                "&sort=stars&order=desc&per_page=3" % q)
        if "__err" in d:
            fails.append("new:%s:%s" % (kw.split()[0], d["__err"]))
            continue
        add(d.get("items") or [], "new", 3)
        time.sleep(1)

    # B 线：月内活跃的「相关」大库（限定 topic，避免 public-apis 这类通用榜霸榜）
    for lab, qs in (("llm", "topic:llm-inference stars:>500"),
                    ("agent", "topic:agent stars:>800"),
                    ("quant", "topic:quantization stars:>300")):
        q = ("%s pushed:>=%s" % (qs, start)).replace(" ", "+")
        d = api("https://api.github.com/search/repositories?q=%s"
                "&sort=stars&order=desc&per_page=4" % q)
        if "__err" in d:
            fails.append("active:%s:%s" % (lab, d["__err"]))
            continue
        add(d.get("items") or [], "active", 2)
        time.sleep(2)

    if not rows:
        sys.stderr.write("ALL_FAIL %s\n" % ",".join(fails))
        return 3

    # 去重（90 天窗口）
    try:
        seen = json.load(io.open(SEEN, encoding="utf-8"))
    except Exception:
        seen = {}
    cut = (now - timedelta(days=90)).strftime("%Y-%m-%d")
    seen = {k: v for k, v in seen.items() if v >= cut}

    fresh, dumped = [], 0
    for r in rows:
        if r["full_name"] in seen:
            dumped += 1
            continue
        fresh.append(r)

    fresh.sort(key=lambda r: -r["stars"])
    new_high = [r for r in fresh if r["line"] == "new"][:5]
    active = [r for r in fresh if r["line"] == "active"][:5]

    L = ["🐙 **GitHub 月度更新 · %s**（近 30 日，起点 %s）" % (stamp, start)]
    L.append("扫 %d 式 · 命中 %d · 去重复现 %d · 失败 %d"
             % (len(KW) + 3, len(rows), dumped, len(fails)))
    L.append("本次投递：新建 %d · 活跃 %d%s"
             % (len(new_high), len(active), "（dry-run，不写台账）" if dry else ""))
    if new_high:
        L.append("\n**新建高星**")
        for r in new_high:
            L.append("- **%s** %s★ %s\n  %s" % (r["full_name"], format(r["stars"], ","),
                                               r["lang"], (r["desc"] or "无简介")[:70]))
    if active:
        L.append("\n**月内活跃（topic 命中，已剔通用库）**")
        for r in active:
            L.append("- **%s** %s★ · 最近推送 %s\n  %s"
                     % (r["full_name"], format(r["stars"], ","), r["pushed"],
                        (r["desc"] or "无简介")[:70]))
    if fails:
        L.append("\n⚠️ 失败式：%s" % "；".join(fails[:6]))

    txt = "\n".join(L)
    if len(txt) > 1400:
        txt = txt[:1390] + "\n…（截断）"
    print(txt)

    # 落盘
    try:
        os.makedirs(AK, exist_ok=True)
        io.open(OUT, "w", encoding="utf-8").write(
            json.dumps({"month": stamp, "start": start,
                        "queries": len(KW) + 3, "rows": rows,
                        "fresh": fresh, "fails": fails},
                       ensure_ascii=False, indent=1))
        if not dry:
            for r in fresh:
                seen[r["full_name"]] = now.strftime("%Y-%m-%d")
            io.open(SEEN, "w", encoding="utf-8").write(
                json.dumps(seen, ensure_ascii=False, indent=1))
    except Exception as e:
        sys.stderr.write("WRITE_FAIL %s\n" % type(e).__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
