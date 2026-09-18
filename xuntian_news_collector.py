# -*- coding: utf-8 -*-
"""巡天·新闻知识采集 v1.0 (2026-08-09)
整合 Horizon 新闻抓取进巡天框架:
  1. 抓取 Horizon 新闻源 (HN/Google News/RSS)
  2. 分类入库 knowledge_base/news/  (按日期)
  3. 输出摘要 (供 cron 推送)

用法: python xuntian_news_collector.py [--days N] [--silent]
"""
# side_effects: [写数据文件]
import os
import sys, io, os, json, subprocess, datetime, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HORIZON = r"D:\hermes\Horizon"
KB_NEWS = r"D:\hermes\hermes-data\profiles\qqbot3\knowledge_base\news"
PY = sys.executable

def fetch_horizon_items():
    """抓取新闻 (AnySearch 搜索 + Horizon 文件兜底)
    ★ R1023 A10: 接入 CollectResult 契约 — 局部失败不升级但显式标记部分性
    """
    items = []
    try:
        from collect_result import CollectResult
        cr = CollectResult("xuntian_news",
                           log_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                "..", "data", "collect_logs"))
    except Exception:
        cr = None
    # 1. 优先: AnySearch 搜索热门新闻 (绕开 Horizon 包结构)
    try:
        cli = r"D:\hermes\hermes-data\profiles\qqbot3\skills\research\anysearch\scripts\anysearch_cli.py"
        if os.path.exists(cli):
            queries = [{"query": "AI 最新突破 2026", "max_results": 5},
                       {"query": "人工智能 重要新闻 今日", "max_results": 5},
                       {"query": "科技 突破性 发现", "max_results": 5}]
            qj = json.dumps(queries)
            r = subprocess.run([sys.executable, cli, "batch_search", "--queries", qj],
                               capture_output=True, text=True, timeout=60,
                               encoding="utf-8", errors="replace")
            if r.returncode == 0 and "## Search Results" in r.stdout:
                import re
                lines = r.stdout.splitlines()
                for i, line in enumerate(lines):
                    if line.strip().startswith("###"):
                        title = line.strip().lstrip("# ").strip()
                        # 清洗: 去编号前缀 "1. " / "2. " / "02：" / "3、"
                        import re as _re
                        # ★ r1194: 原正则只覆盖 "." ⇒ 漏全角冒号/顿号形态
                        #   🟢 实测漏了 "02：2026、2026年AI 最新發展趨勢介紹"
                        title = _re.sub(r"^\d+\s*[.．。：:、]\s*", "", title).strip()
                        # ★ 去【栏目】/丨 前缀(如 "全文丨…"、"【科技观察】…")
                        title = _re.sub(r"^【[^】]{0,14}】\s*", "", title).strip()
                        title = _re.sub(r"^[^丨|]{0,10}[丨|]\s*", "", title).strip()
                        # 过滤导航/站点名 (无实际内容)
                        # ★ r1194 修复: 原来是【枚举式黑名单】⇒ 遇到没枚举过的新站点必漏。
                        #   🟢 实测 2026-09-18 漏了:
                        #     "AI最新资讯_人工智能新闻头条 - AI NEWS - AIBase"
                        #     "人工智慧- BBC News 中文"
                        #   且 `len(title) < 12` 在真实数据上【完全无效】(实测最短 13)。
                        #   ⇒ 补【结构性判据】(不依赖站点清单):
                        #     (a) 尾部站点标识  例 "… - AI NEWS - AIBase" / "…_xxx"
                        #     (b) 栏目/导航词    例 "AI最新资讯" / "头条" / "频道"
                        nav_keywords = ("TechNews 科技新報|", "科技新闻_", "Reuters",
                                        "纽约时报中文网", "科技相关报道", "科技 |",
                                        "市場和業內人士", "Today's Latest", "央视网",
                                        "BBC News", "AI NEWS", "AIBase", "AIHOT",
                                        "AASTOCKS", "新浪", "搜狐", "网易", "腾讯新闻")
                        if any(k in title for k in nav_keywords):
                            continue
                        # ★ (a) 尾部站点标识: 结尾是 " - <英文/站点名>" 或 "_<站点名>"
                        if _re.search(r"(\s[-_|]\s|[_\|])[A-Za-z][A-Za-z0-9 .&\-]{2,}\s*$", title):
                            continue
                        # ★ (b) 栏目/导航词(中文站点通用栏目名, 非具体新闻事件)
                        if _re.search(r"(新闻中心|新聞中心|出版品|月刊|排行榜|專題|专题|"
                                      r"官網|官网|頻道|频道|首頁|首页|欄目|栏目|導航|导航)", title):
                            continue
                        # ★ (c) r1194 补: 栏目页的两类漏网形态
                        #   (i)  "今日AI新闻| 每天看懂AI 行业新变化"  ← "新闻|" + 标语
                        #   (ii) "AI最新资讯_人工智能新闻头条"        ← "最新资讯"/"资讯_"
                        if _re.search(r"(新闻|新聞|资讯|資訊)\s*[丨|]", title):
                            continue
                        if _re.search(r"(最新资讯|最新資訊|新闻头条|新聞頭條|"
                                      r"行业新变化|行業新變化|每日动态|每日動態)", title):
                            continue
                        if len(title) < 12:
                            continue
                        url = ""
                        for nl in lines[i+1:i+3]:
                            if nl.strip().startswith("- **URL**"):
                                url = "http" + nl.strip().split("http", 1)[-1]
                        items.append({"source": "anysearch", "title": title[:100],
                                      "url": url, "score": 50})
                        if len(items) >= 12:
                            break
        if cr:
            cr.ok("anysearch", len([x for x in items if x.get("source")=="anysearch"]))
    except Exception as e:
        print(f"  ⚠️ AnySearch 抓取失败: {str(e)[:60]}")
        if cr:
            cr.fail("anysearch", str(e))
    # 2. 兜底: 读 Horizon 摘要
    # ★ r1194 修复(调度顺序死锁): Horizon 摘要在 08:30 生成(cron 92c2c8149fdb "30 8 * * *"),
    #   而本采集原在 06:20 ⇒ 【永远】早于摘要生成 ⇒ horizon 源恒失败:
    #     "今日摘要文件不存在: horizon-2026-09-18-en.md"
    #   🟢 实测证据: horizon-2026-09-18-en.md mtime=08:32, 采集在 06:20/08:06。
    #   修法(两面): ① cron 时刻后移(另改) ② 本处加【多天回退】兜底。
    try:
        import re
        today = datetime.date.today()
        horizon_file = None
        horizon_used = None
        # 今日 → 昨日 → 前日(摘要可能延迟或当天缺失)
        for back in (0, 1, 2):
            d = (today - datetime.timedelta(days=back)).isoformat()
            cand = os.path.join(HORIZON, "data", "summaries", f"horizon-{d}-en.md")
            if os.path.exists(cand):
                horizon_file, horizon_used = cand, d
                break
        if horizon_file:
            content = open(horizon_file, encoding="utf-8", errors="replace").read()
            n0 = len(items)
            for m in re.finditer(r"\*\*(.+?)\*\*", content):
                title = m.group(1).strip()
                if len(title) > 10 and "Horizon" not in title:
                    items.append({"source": "horizon", "title": title[:100],
                                  "url": "", "score": 30})
                    if len(items) >= 15:
                        break
            n_add = len(items) - n0
            if cr:
                cr.ok("horizon", n_add)
            if horizon_used != today.isoformat():
                print("  ℹ️ Horizon 用回退日期 %s(今日摘要尚未生成)" % horizon_used)
        else:
            if cr:
                cr.fail("horizon", "近 3 日均无摘要文件")
    except Exception as e:
        # ★ R1023 A10: 原为 `except: pass` — 静默失败! 现显式记录
        print(f"  ⚠️ Horizon 读取失败: {str(e)[:60]}")
        if cr:
            cr.fail("horizon", str(e))

    # ★ R1023 A10: 显式输出部分性状态 (局部失败不升级, 但必须可见)
    if cr:
        # 确保 anysearch 源被记录 (若上面 try 未走到记录点)
        if not any(s["source"] == "anysearch" for s in cr.sources):
            cr.ok("anysearch", len([x for x in items if x.get("source") == "anysearch"]))
        res = cr.finish()
        if res["status"] != "ok":
            print(cr.summary())
    return items

def save_to_kb(items, date_str):
    """入库 knowledge_base/news/YYYY-MM-DD.json"""
    os.makedirs(KB_NEWS, exist_ok=True)
    path = os.path.join(KB_NEWS, f"news_{date_str}.json")
    # 合并已有 (去重 by url)
    existing = {}
    if os.path.exists(path):
        try:
            existing = {x["url"]: x for x in json.load(open(path, encoding="utf-8"))}
        except Exception:
            pass
    for it in items:
        if it["url"] and it["url"] not in existing:
            existing[it["url"]] = it
    if os.path.exists(path):
        if os.path.exists(path + ".bak"):
            try: os.remove(path + ".bak")
            except OSError: pass
        os.rename(path, path + ".bak")
    json.dump(list(existing.values()), open(path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return path, len(existing)

def main():
    days = 1
    if "--days" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1])

    today = datetime.date.today()
    print(f"=== 巡天·新闻采集 ===")
    print(f"日期: {today}")

    total_new = 0
    for d in range(days):
        date_str = (today - datetime.timedelta(days=d)).isoformat()
        print(f"\n[{date_str}] 抓取新闻源...")
        items = fetch_horizon_items()
        print(f"  抓取: {len(items)} 条 (HN + Google News)")
        path, count = save_to_kb(items, date_str)
        print(f"  入库: {count} 条 → {os.path.basename(path)}")

    # 摘要输出
    latest = sorted(glob.glob(os.path.join(KB_NEWS, "news_*.json")))[-1]
    data = json.load(open(latest, encoding="utf-8"))
    data.sort(key=lambda x: x.get("score", 0), reverse=True)
    print(f"\n📰 巡天·新闻速览 ({len(data)} 条, 最新 {os.path.basename(latest)})")
    for it in data[:8]:
        title = it.get("title", "")[:60]
        src = it.get("source", "")
        score = it.get("score", 0)
        print(f"  [{src}] ({score}) {title}")

if __name__ == "__main__":
    main()
