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
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
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
                        # ★ 2026-09-26 修复: 原窗口 lines[i+1:i+3] 只覆盖 2 行 ⇒ 上游一旦在标题与
                        #   URL 之间多出任何一行(或块结构变化), url 恒为空 ⇒ save_to_kb 按 url
                        #   去重时【静默丢弃】⇒ 落盘写成 []。🟢 实测: 09-25/09-26 连续两天 news
                        #   落盘 0 条(此前 9-11 条), 而日志仍打印「抓取: 15 条」= 漏采伪装成正常。
                        #   改为扫到【本块结束】(下一个 ### 即 break), 不会跨块误取下一块的 URL。
                        for nl in lines[i + 1:i + 12]:
                            if nl.strip().startswith("###"):
                                break
                            if nl.strip().startswith("- **URL**"):
                                url = "http" + nl.strip().split("http", 1)[-1]
                                break
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
    added = 0   # ★ 2026-09-26: 本轮真正新增的条数 (残差判据必须用它, 不能用文件总数)
    dropped_empty_url = 0   # ★ 2026-09-28: 因 url 为空被丢弃的条数 (horizon 兜底源即此形态)
    dropped_dup = 0         # ★ 2026-09-28: 因 url 重复被跳过的条数 (正常幂等, 不是缺陷)
    for it in items:
        # ★ 2026-09-28 修复: 原写法 `if it["url"] and it["url"] not in existing` 把
        #   【空 url】与【重复 url】两种丢弃混为一个静默分支 ⇒ 丢弃量不可见。
        #   实测当日: horizon 源条目 url 恒为空 ⇒ 抓取 15 / 入库 9, 6 条被吞且零告警。
        #   ★ 两者必须分开计数: 空 url 丢弃 = 缺陷信号; 重复丢弃 = 幂等正常行为。
        #     否则「当日文件已有内容时重跑 ⇒ added=0」会被误判成「全部丢弃」而假告警。
        if not it.get("url"):
            dropped_empty_url += 1
            continue
        if it["url"] not in existing:
            existing[it["url"]] = it
            added += 1
        else:
            dropped_dup += 1
    if os.path.exists(path):
        if os.path.exists(path + ".bak"):
            try: os.remove(path + ".bak")
            except OSError: pass
        os.rename(path, path + ".bak")
    json.dump(list(existing.values()), open(path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return path, len(existing), added, dropped_empty_url, dropped_dup

def main():
    days = 1
    if "--days" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1])

    today = datetime.date.today()
    print(f"=== 巡天·新闻采集 ===")
    print(f"日期: {today}")

    total_new = 0
    guard_failed = False   # ★ 2026-09-26 残差守卫标志 (抓到 >0 但入库 ==0 ⇒ 判失败)
    for d in range(days):
        date_str = (today - datetime.timedelta(days=d)).isoformat()
        print(f"\n[{date_str}] 抓取新闻源...")
        items = fetch_horizon_items()
        # ★ 2026-09-28 修复: 原文案硬编码 "(HN + Google News)" —— 本采集器的真实数据源是
        #   【AnySearch 搜索 + Horizon 摘要兜底】(见模块 docstring), 从不抓 HN/Google News。
        #   该错误文案已【造成实际误诊】: 2026-09-28 新闻早报据此报出「日志称抓取 15 条
        #   (HN + Google News), 但落盘只有 9 条且全为 anysearch —— HN/Google News 未持久化」,
        #   把「文案写错 + horizon 空 url 被丢」误读成「HN/Google News 采集后未落盘」。
        src_cnt = {}
        for it in items:
            s = it.get("source", "?")
            src_cnt[s] = src_cnt.get(s, 0) + 1
        src_desc = " + ".join(f"{k} {v} 条" for k, v in sorted(src_cnt.items())) or "0 条"
        print(f"  抓取: {len(items)} 条 (分源: {src_desc})")
        path, count, added, dropped, dup = save_to_kb(items, date_str)
        print(f"  入库: 本轮新增 {added} 条 / 文件共 {count} 条 → {os.path.basename(path)}")
        if dropped or dup:
            print(f"  未入库明细: 空 url 丢弃 {dropped} 条 | 重复跳过 {dup} 条"
                  f" (抓取 {len(items)} = 新增 {added} + 丢弃 {dropped} + 重复 {dup})")
        # ★ 2026-09-26 修复: 残差守卫。原实现「抓取 N 条 / 入库 0 条」两个数自相矛盾
        #   仍 exit 0, 文件被写成 [] 而调用方看不出失败 (实测连续两天静默漏采)。
        #   ★ 判据必须用【本轮新增 added】, 不能用 count(文件总数) —— 否则当日文件
        #     已有旧内容时, 「本轮全丢」会被旧条目掩盖而漏报。
        if len(items) > 0 and added == 0 and dropped > 0:
            print(f"  🔴 残差告警: 本轮抓取 {len(items)} 条, 但新增 0 条 —— "
                  f"{dropped} 条全部因 url 为空被丢弃")
            guard_failed = True
        elif dropped and dropped >= max(1, len(items) // 2):
            # ★ 2026-09-28 修复: 原守卫只挡【全丢】(added == 0), 掩盖了【部分丢弃】。
            #   实测当日: 抓取 15 / 入库 9 ⇒ 6 条 (horizon 源, url 恒为空) 被静默丢弃,
            #   无任何告警 ⇒ 与「漏采伪装成正常」同族。丢弃 ≥ 半数即视为该源整体失效。
            print(f"  🟠 残差告警: {len(items)} 条中 {dropped} 条因 url 为空被丢弃 (≥ 半数)"
                  f" —— 该源可能整体失效 (horizon 兜底源的 url 恒为空)")
            guard_failed = True
        # ★ 2026-09-28 补漏: 上面两条守卫都以 `len(items) > 0` 为前提 ⇒ 抓取【一条都没
        #   抓到】时全部落空, 而 save_to_kb 在 existing 为空时会把 `[]` 写进当日文件并
        #   exit 0 —— 这正是历史上 6 个 2 字节空档文件 (08-26/09-04/09-10/09-15/09-16/
        #   09-25) 的成因。判据: 同一日 trend_*.json 稳定产出 51 条 ⇒ 「0 条」不可能是
        #   「当日确实无内容」, 只能是采集失败 (DNS/代理/上游全挂), 必须判失败。
        if len(items) == 0:
            print("  🔴 零采集告警: 本轮抓取 0 条 —— 同日 trend 源稳定有产出, "
                  "故这不是「当日无内容」而是采集失败")
            guard_failed = True

    # 摘要输出
    latest = sorted(glob.glob(os.path.join(KB_NEWS, "news_*.json")))[-1]
    data = json.load(open(latest, encoding="utf-8"))
    # ★ 2026-09-28 如实标注: `score` 是【来源优先级占位值】(anysearch=50 / horizon=30, 均为硬编码
    #   常量), 【不是】质量分或相关度分。同源条目 score 全同 ⇒ 该排序对同源内部【无区分力】
    #   (仅靠 Python 稳定排序保持原序)。下游若把 score 当质量信号使用即为误用。
    data.sort(key=lambda x: x.get("score", 0), reverse=True)
    print(f"\n📰 巡天·新闻速览 ({len(data)} 条, 最新 {os.path.basename(latest)})")
    for it in data[:8]:
        title = it.get("title", "")[:60]
        src = it.get("source", "")
        score = it.get("score", 0)
        print(f"  [{src}] ({score}) {title}")

    # ★ 2026-09-26: 残差守卫必须转成非零退出码 —— 否则 cron 记 ok 而当日知识静默丢失
    if guard_failed:
        print("\n🔴 本次采集判为失败 (残差守卫): 抓到条目但入库 0 条")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
