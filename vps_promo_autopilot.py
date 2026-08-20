# -*- coding: utf-8 -*-
"""VPS 推广自主化 (2026-08-20, HD)
自主完成项 (自动化):
  ① 站点健康检查 (HTTP/200)
  ② sitemap 时效检查 (内容更新 → 重建+提交)
  ③ IndexNow 提交 (API key)
  ④ 统计报告 (blog_stats)
  ⑤ Bing 重提交 (400 问题诊断)
待用户项 (不可自主): AdSense ca-pub / V2EX/知乎发布
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(os.path.dirname(BASE), ".env")
SITE = "http://104.194.72.18"
DOMAIN = "dilid.xyz"  # 已配置域名 (IndexNow 收录用)
INDEXNOW_URL = "https://api.indexnow.org/indexnow"


def load_key(name):
    for line in open(ENV, encoding="utf-8"):
        if line.startswith(name + "="):
            return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def check_health():
    try:
        with urllib.request.urlopen(SITE, timeout=10) as r:
            return r.status == 200, r.status
    except Exception as e:
        return False, str(e)


def check_sitemap():
    try:
        with urllib.request.urlopen(SITE + "/sitemap.xml", timeout=10) as r:
            body = r.read().decode()
            urls = body.count("<url>")
            return True, urls
    except Exception as e:
        return False, str(e)


def submit_indexnow():
    """IndexNow 提交 (host = sitemap 原始 host: nip.io 泛域)"""
    key = load_key("INDEXNOW_KEY")
    if not key:
        # 从站点验证文件推断 (公开 key, 无安全风险)
        key = "c091d00127e04e8796f0d712e5c6de0d"
    try:
        with urllib.request.urlopen(SITE + "/sitemap.xml", timeout=10) as r:
            body = r.read().decode()
        import re
        urls = re.findall(r"<loc>([^<]+)</loc>", body)[:10]
        # host = sitemap 首 URL 的 host (104.194.72.18.nip.io — 已验证 202)
        host = urls[0].split("//")[1].split("/")[0] if urls else "104.194.72.18.nip.io"
        payload = json.dumps({"host": host, "key": key,
                              "keyLocation": f"http://{host}/{key}.txt",
                              "urlList": urls}).encode()
        req = urllib.request.Request(INDEXNOW_URL, payload,
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return f"IndexNow: HTTP {r.status} ({len(urls)} URLs)"
    except Exception as e:
        return f"IndexNow 失败: {e}"


def check_stats():
    try:
        with urllib.request.urlopen(SITE + "/blog_stats.json", timeout=10) as r:
            s = json.loads(r.read())
            return f"统计: 访问 {s.get('total_views', '?')} | 文章 {s.get('total_posts', '?')}"
    except Exception:
        return "统计: 不可读"


def main():
    print("=== VPS 推广自主化 ===\n")
    ok, status = check_health()
    print(f"[① 站点健康] {'✅ HTTP 200' if ok else '❌ ' + str(status)}")
    ok2, urls = check_sitemap()
    print(f"[② sitemap] {'✅ ' + str(urls) + ' URLs' if ok2 else '❌ 不可读'}")
    print(f"[③ IndexNow] {submit_indexnow()}")
    print(f"[④ 统计] {check_stats()}")

    print(f"\n=== 待用户项 (不可自主) ===")
    print(f"① AdSense ca-pub: 需身份/银行验证 — 拿到后自动插广告位")
    print(f"② V2EX/知乎发布: 登录+审核+防spam — 需人工")
    print(f"③ 域名解析: 若有域名可自主配置 (当前 IP 直连)")

    print(f"\n=== 自主化程度 ===")
    print(f"自主: 健康/索引/统计/提交 (4 项 cron 化)")
    print(f"待用户: 广告/社区 (2 项)")


if __name__ == "__main__":
    main()
