#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daily_news_2026_09_17.py -- 七领域每日新闻采集 (cron)"""
import json, re, sys, time, warnings
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests, feedparser
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")
PROXY = {"http": "socks5h://127.0.0.1:10808", "https": "socks5h://127.0.0.1:10808"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HDR = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8"}

OUT = {}


def get(url, timeout=30, headers=None, direct_first=True):
    h = dict(HDR)
    if headers:
        h.update(headers)
    for proxies in ([None, PROXY] if direct_first else [PROXY]):
        try:
            r = requests.get(url, headers=h, proxies=proxies, timeout=timeout, verify=False)
            if r.status_code == 200 and len(r.content) > 200:
                return r
        except Exception:
            continue
    return None


def gnews(query, n=8, hl="en-US", gl="US", ceid="US:en"):
    """Google News RSS -> list of {title, source, date, url}"""
    url = (f"https://news.google.com/rss/search?q={quote(query)}"
           f"&hl={hl}&gl={gl}&ceid={ceid}")
    r = get(url)
    if not r:
        return []
    out = []
    try:
        f = feedparser.parse(r.content)
        for e in f.entries[:n]:
            title = e.get("title", "")
            src = ""
            m = re.search(r" - ([^-]+)$", title)
            if m:
                src = m.group(1).strip()
                title = title[: m.start()].strip()
            out.append({
                "title": title, "source": src,
                "date": e.get("published", "")[:16],
                "url": e.get("link", ""),
            })
    except Exception as ex:
        print(f"  [gnews parse err] {ex}", file=sys.stderr)
    return out


def arxiv(query, n=8, days=7):
    url = ("https://export.arxiv.org/api/query?search_query=" + quote(query) +
           f"&sortBy=submittedDate&sortOrder=descending&max_results={n*2}")
    r = get(url)
    if not r:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    try:
        f = feedparser.parse(r.content)
        for e in f.entries:
            pub = e.get("published", "")
            try:
                dt = datetime.strptime(pub[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if dt < cutoff:
                continue
            out.append({
                "title": re.sub(r"\s+", " ", e.get("title", "")).strip(),
                "date": pub[:10],
                "url": e.get("link", ""),
                "summary": re.sub(r"\s+", " ", e.get("summary", ""))[:300],
            })
            if len(out) >= n:
                break
    except Exception as ex:
        print(f"  [arxiv parse err] {ex}", file=sys.stderr)
    return out


def rss(url, n=8):
    r = get(url)
    if not r:
        return []
    out = []
    try:
        f = feedparser.parse(r.content)
        for e in f.entries[:n]:
            out.append({"title": re.sub(r"\s+", " ", e.get("title", "")).strip(),
                        "date": e.get("published", "")[:16], "url": e.get("link", "")})
    except Exception:
        pass
    return out


# ============================== 1. 病毒学 ==============================
print("[1/6] 病毒学 ...")
VIRUS = {}
VIRUS["covid_variant"] = gnews(
    'COVID-19 variant OR "SARS-CoV-2" new variant surveillance', 8)
VIRUS["influenza"] = gnews(
    'influenza OR "H5N1" OR "bird flu" H5N5 outbreak 2026', 8)
VIRUS["who_cdc"] = gnews(
    '(site:who.int OR site:cdc.gov OR site:ecdc.europa.eu) disease outbreak', 8)
VIRUS["epi_risk"] = gnews(
    'pandemic preparedness OR "public health emergency" WHO 2026', 6)
# WHO official pages
for name, u in [
    ("who_don", "https://www.who.int/emergencies/disease-outbreak-news"),
    ("who_newsroom", "https://www.who.int/news-room/releases"),
]:
    r = get(u, timeout=35)
    if r:
        try:
            s = BeautifulSoup(r.text, "lxml")
            items = []
            for a in s.select("a")[:400]:
                t = a.get_text(" ", strip=True)
                href = a.get("href", "")
                if t and 30 < len(t) < 160 and "/item/" in href or "/news/" in href:
                    items.append({"title": t, "url": href if href.startswith("http") else "https://www.who.int" + href})
                if len(items) >= 8:
                    break
            VIRUS[name] = items
        except Exception as ex:
            print(f"  [who {name} err] {ex}", file=sys.stderr)
OUT["virus"] = VIRUS

# ============================== 2/5. AI + 论文 ==============================
print("[2/6] AI 进展 & 论文 ...")
AI = {}
AI["arxiv_llm"] = arxiv('cat:cs.CL AND abs:"large language model"', 8, 7)
AI["arxiv_agent"] = arxiv('abs:"agent" AND abs:"LLM"', 6, 7)
AI["arxiv_multimodal"] = arxiv('abs:"multimodal" OR abs:"vision-language"', 6, 7)
AI["arxiv_diffusion"] = arxiv('abs:"diffusion model"', 6, 7)
AI["arxiv_rl"] = arxiv('abs:"reinforcement learning" AND cat:cs.LG', 6, 7)
AI["arxiv_transformer"] = arxiv('abs:"transformer" AND abs:"efficient"', 5, 7)
AI["arxiv_gnn"] = arxiv('abs:"graph neural network" OR abs:"graph transformer"', 5, 7)

BLOGS = [
    ("OpenAI", "https://openai.com/news/rss.xml"),
    ("Google DeepMind", "https://deepmind.google/blog/rss.xml"),
    ("Google AI", "https://blog.google/technology/ai/rss/"),
    ("Microsoft Research", "https://www.microsoft.com/en-us/research/blog/feed/"),
    ("BAIR Berkeley", "https://bair.berkeley.edu/blog/feed.xml"),
    ("HuggingFace", "https://huggingface.co/blog/feed.xml"),
    ("MIT News AI", "https://news.mit.edu/rss/topic/artificial-intelligence2"),
]
AI["blogs"] = {}
for nm, u in BLOGS:
    items = rss(u, 5)
    if items:
        AI["blogs"][nm] = items
AI["ai_news"] = gnews('AI model release OR "large language model" announcement', 8)
OUT["ai"] = AI

# ============================== 3. GitHub ==============================
print("[3/6] GitHub 热门 ...")
GH = {}
try:
    week_ago = (datetime.now(timezone.utc) - timedelta(days=9)).strftime("%Y-%m-%d")
    r = get(f"https://api.github.com/search/repositories?q=created:>{week_ago}&sort=stars&order=desc&per_page=15",
            headers={"Accept": "application/vnd.github+json"})
    if r:
        GH["new_rising"] = [{
            "name": x["full_name"], "stars": x["stargazers_count"],
            "lang": x.get("language"), "desc": (x.get("description") or "")[:150],
            "url": x["html_url"], "created": x.get("created_at", "")[:10],
        } for x in r.json().get("items", [])]
except Exception as ex:
    print(f"  [gh api err] {ex}", file=sys.stderr)

try:
    r = get("https://github.com/trending?since=daily")
    if r:
        s = BeautifulSoup(r.text, "lxml")
        tr = []
        for art in s.select("article.Box-row")[:15]:
            a = art.select_one("h2 a")
            if not a:
                continue
            name = "/".join(a.get("href", "").strip("/").split("/")[:2])
            desc = art.select_one("p")
            star = art.select_one("a[href$='/stargazers']")
            lang = art.select_one("[itemprop=programmingLanguage]")
            tr.append({
                "name": name,
                "desc": desc.get_text(" ", strip=True)[:150] if desc else "",
                "stars": star.get_text(strip=True) if star else "",
                "lang": lang.get_text(strip=True) if lang else "",
                "url": "https://github.com/" + name,
            })
        GH["trending_daily"] = tr
except Exception as ex:
    print(f"  [gh trending err] {ex}", file=sys.stderr)

try:
    r = get("https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=20")
    if r:
        GH["hn_front"] = [{"title": h.get("title"),
                           "points": h.get("points"),
                           "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"}
                          for h in r.json().get("hits", []) if h.get("title")][:12]
except Exception as ex:
    print(f"  [hn err] {ex}", file=sys.stderr)
OUT["github"] = GH

# ============================== 4. 锂电 ==============================
print("[4/6] 锂电 ...")
LI = {}
LI["arxiv_battery"] = arxiv('abs:"lithium" AND (abs:"battery" OR abs:"anode" OR abs:"cathode")', 8, 7)
LI["arxiv_solid"] = arxiv('abs:"solid-state" AND abs:"battery"', 6, 7)
LI["arxiv_silicon"] = arxiv('abs:"silicon anode" OR abs:"lithium metal anode"', 6, 7)
LI["arxiv_li_s"] = arxiv('abs:"lithium-sulfur" OR abs:"Li-S battery"', 5, 7)
LI["arxiv_li_air"] = arxiv('abs:"lithium-air" OR abs:"Li-air" OR abs:"lithium-oxygen"', 5, 14)
LI["price"] = gnews('碳酸锂 价格 行情 OR lithium carbonate price', 8, hl="zh-CN", gl="CN", ceid="CN:zh-Hans")
LI["industry"] = gnews('锂电池 OR 固态电池 OR 硅碳负极 行业动态', 8, hl="zh-CN", gl="CN", ceid="CN:zh-Hans")
LI["global"] = gnews('lithium battery solid-state EV battery news', 8)
OUT["lithium"] = LI

# ============================== 6. 科技财经 ==============================
print("[5/6] 科技财经 ...")
TECH = {}
TECH["bigtech"] = gnews('Nvidia OR TSMC OR Apple OR Microsoft earnings semiconductor', 8)
TECH["china_tech"] = gnews('科技巨头 OR 半导体 OR 新能源 政策 财报', 8, hl="zh-CN", gl="CN", ceid="CN:zh-Hans")
TECH["energy_policy"] = gnews('new energy policy OR EV subsidy OR battery regulation', 6)
TECH["markets"] = gnews('stock market tech sector Nasdaq', 5)
OUT["tech"] = TECH

# ============================== 7. 额外: 综合头条 ==============================
print("[6/6] 综合头条 ...")
OUT["headlines"] = gnews('breaking news world', 8)
OUT["china_pengpai_check"] = gnews('澎湃新闻 今日要闻', 6, hl="zh-CN", gl="CN", ceid="CN:zh-Hans")

OUT["_meta"] = {"generated": datetime.now(timezone.utc).isoformat(), "date": "2026-09-17"}

with open("D:/hermes/analysis/_daily_news_raw.json", "w", encoding="utf-8") as f:
    json.dump(OUT, f, ensure_ascii=False, indent=1)

# 打印摘要供阅读
def show(tag, items, k="title"):
    print(f"\n--- {tag} ---")
    for i, it in enumerate(items[:8], 1):
        if isinstance(it, dict):
            d = it.get("date", "")
            s = it.get("source", it.get("lang", ""))
            print(f"{i}. [{d}] {it.get(k,'')}  ({s})")
            if it.get("url"):
                print(f"   {it['url']}")
            if it.get("desc"):
                print(f"   {it['desc']}")

show("COVID变种", VIRUS.get("covid_variant", []))
show("流感/H5N1", VIRUS.get("influenza", []))
show("WHO/CDC", VIRUS.get("who_cdc", []))
show("WHO DON页面", VIRUS.get("who_don", []))
def showar(tag, items):
    print(f"\n--- {tag} ---")
    for i, it in enumerate(items, 1):
        print(f"{i}. [{it.get('date','')}] {it.get('title','')}")
        print(f"   {it.get('url','')}")
showar("arXiv LLM", AI.get("arxiv_llm", []))
showar("arXiv Agent", AI.get("arxiv_agent", []))
showar("arXiv 多模态", AI.get("arxiv_multimodal", []))
showar("arXiv Diffusion", AI.get("arxiv_diffusion", []))
showar("arXiv RL", AI.get("arxiv_rl", []))
show("AI公司博客", [{"title": f"[{k}] {e['title']}", "date": e['date'], "url": e['url']}
                    for k, v in AI.get("blogs", {}).items() for e in v])
show("GitHub新星", GH.get("new_rising", []), "name")
show("GitHub Trending", GH.get("trending_daily", []), "name")
showar("锂电arXiv", LI.get("arxiv_battery", []))
showar("固态电池arXiv", LI.get("arxiv_solid", []))
showar("硅负极arXiv", LI.get("arxiv_silicon", []))
showar("Li-S arXiv", LI.get("arxiv_li_s", []))
showar("Li-air arXiv", LI.get("arxiv_li_air", []))
show("锂价", LI.get("price", []))
show("锂电行业", LI.get("industry", []))
show("锂电全球", LI.get("global", []))
show("科技巨头", TECH.get("bigtech", []))
show("中国科技", TECH.get("china_tech", []))
show("能源政策", TECH.get("energy_policy", []))
show("综合头条", OUT.get("headlines", []))
print("\n\nRAW JSON: D:/hermes/analysis/_daily_news_raw.json")
