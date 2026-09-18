#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clean_news_noise.py — 用【与采集器相同的结构性判据】清理已入库的噪声条目

★ 为什么需要(r1194):
    采集器是【增量合并】(existing = {x["url"]: x ...} 保留旧条目)
    ⇒ ★ 过滤规则改进后, 【已入库的旧噪声】不会被回溯清除。
    ⇒ 本脚本用同一套判据扫一遍当日文件, 移出噪声(移入 .noise.json 而非直接删)。

★ 判据必须与 xuntian_news_collector.py 保持一致 —— 单一真相源在那边。
"""
import io
import json
import os
import re as _re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NAV = ("TechNews 科技新報|", "科技新闻_", "Reuters", "纽约时报中文网", "科技相关报道",
       "科技 |", "市場和業內人士", "Today's Latest", "央视网", "BBC News", "AI NEWS",
       "AIBase", "AIHOT", "AASTOCKS", "新浪", "搜狐", "网易", "腾讯新闻")


def clean_title(t):
    """★ r1194: 与 xuntian_news_collector.py 的标题清洗保持一致(单一真相源在那)
    🟢 实测需要: '02：…' / '全文丨…' / '【科技观察】…' 三类前缀"""
    t = _re.sub(r"^\d+\s*[.．。：:、]\s*", "", t).strip()
    t = _re.sub(r"^【[^】]{0,14}】\s*", "", t).strip()
    t = _re.sub(r"^[^丨|]{0,10}[丨|]\s*", "", t).strip()
    return t


def is_noise(title):
    """返回 (是否噪声, 原因)"""
    if any(k in title for k in NAV):
        return True, "黑名单"
    if _re.search(r"(\s[-_|]\s|[_\|])[A-Za-z][A-Za-z0-9 .&\-]{2,}\s*$", title):
        return True, "尾部站点标识"
    if _re.search(r"(新闻中心|新聞中心|出版品|月刊|排行榜|專題|专题|官網|官网|"
                  r"頻道|频道|首頁|首页|欄目|栏目|導航|导航)", title):
        return True, "栏目词"
    # ★ r1194 (c): 栏目页漏网形态
    if _re.search(r"(新闻|新聞|资讯|資訊)\s*[丨|]", title):
        return True, "栏目页(新闻|标语)"
    if _re.search(r"(最新资讯|最新資訊|新闻头条|新聞頭條|"
                  r"行业新变化|行業新變化|每日动态|每日動態)", title):
        return True, "栏目词(资讯/头条)"
    if len(title) < 12:
        return True, "过短"
    return False, ""


def clean(path, dry=True):
    if not os.path.exists(path):
        print("  🔴 不存在: %s" % path)
        return 0, 0
    d = json.load(io.open(path, encoding="utf-8"))
    keep, noise = [], []
    n_fixed = 0
    for x in d:
        t0 = x.get("title", "")
        # ★★ r1194 顺序修正: 必须【先在原始标题上判噪声】, 再清洗。
        #   反例(实测): "今日AI新闻| 每天看懂AI 行业新变化"
        #     → 若先清洗(去丨前缀)会变成 "每天看懂AI 行业新变化"
        #     → 判别特征("新闻")被删 ⇒ ★ 本该被栏目词拦下的条目反而逃逸。
        bad, why = is_noise(t0)
        t = clean_title(t0)
        if t != t0:
            n_fixed += 1
        if bad:
            noise.append(dict(x, title=t0, _noise_reason=why))
        else:
            x = dict(x)
            x["title"] = t
            keep.append(x)
    print("  文件: %s" % os.path.basename(path))
    print("    原有 %d 条 ⇒ 保留 %d / 移出噪声 %d | 标题清洗 %d 条" %
          (len(d), len(keep), len(noise), n_fixed))
    for x in noise:
        print("      🔴 [%s] %s" % (x.get("_noise_reason", "?"), x.get("title", "")[:58]))
    # ★ r1194 修: 原来写作 `if not dry and noise:` ⇒ noise 为空时【不写回】
    #   ⇒ 纯"标题清洗"(无噪声可移)的结果会丢失。改为只看 dry。
    if not dry:
        if noise:
            bak = path + ".bak_r1194"
            if not os.path.exists(bak):
                io.open(bak, "w", encoding="utf-8", newline="\n").write(
                    io.open(path, encoding="utf-8").read())
                print("    ✅ 已备份 %s" % os.path.basename(bak))
        io.open(path, "w", encoding="utf-8", newline="\n").write(
            json.dumps(keep, ensure_ascii=False, indent=2))
        print("    ✅ 已写回 %d 条(含标题清洗 %d 条)" % (len(keep), n_fixed))
        if noise:
            np = path.replace(".json", ".noise.json")
            io.open(np, "w", encoding="utf-8", newline="\n").write(
                json.dumps([{k: v for k, v in x.items() if k != "_noise_reason"}
                            for x in noise], ensure_ascii=False, indent=2))
            print("    ✅ 噪声移至 %s (%d 条)" % (os.path.basename(np), len(noise)))
    return len(keep), len(noise)


if __name__ == "__main__":
    import datetime
    DRY = "--apply" not in sys.argv
    ALL = "--all-days" in sys.argv
    print("  模式: %s | 范围: %s" % ("🔍 DRY-RUN" if DRY else "⚠️ APPLY",
                                    "全库(--all-days)" if ALL else "★ 仅当天"))
    KB = r"D:\hermes\hermes-data\profiles\qqbot3\knowledge_base\news"
    today = datetime.date.today().isoformat()
    tot_k = tot_n = 0
    for f in sorted(os.listdir(KB)):
        if not (f.startswith("news_") and f.endswith(".json")) or "noise" in f:
            continue
        # ★ 默认只清当天 —— 历史文件属归档, 不擅自改动
        if not ALL and today not in f:
            continue
        k, n = clean(os.path.join(KB, f), dry=DRY)
        tot_k += k
        tot_n += n
        print()
    print("  ★ 合计: 保留 %d / 噪声 %d" % (tot_k, tot_n))
    if not ALL:
        print("  (仅当天; 全库清理需显式 --all-days)")
