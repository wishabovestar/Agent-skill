#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ai_frontier_collector.py -- 双通道前沿采集

  通道 1  arXiv 开源论文：按主题查询 arXiv API，取最近 N 天，标注是否有开源代码
  通道 2  AI 公司博客：抓取各实验室 RSS / 新闻页，取最近 N 天

特性
  - 直连优先，失败自动经 SOCKS5 127.0.0.1:10808 重试（GFW 兜底）
  - 按 id/url 的 MD5 去重，归档在 D:/hermes/data/intel/ai_frontier/
  - 输出 JSONL（机器可读）+ Markdown（人读摘要）
  - 每个源独立 try/except，单源失败不影响整体

用法
  python ai_frontier_collector.py                 # 论文+博客，最近 7 天
  python ai_frontier_collector.py --days 3
  python ai_frontier_collector.py --papers-only
  python ai_frontier_collector.py --blogs-only
  python ai_frontier_collector.py --quiet         # 只写文件，不打印摘要
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlencode
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(r"D:\hermes\data\intel\ai_frontier")
ARCHIVE = BASE / "_seen.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

NS = {
    "a": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# ----------------------------------------------------------------------------- arXiv 主题
# (标签, arXiv 查询表达式)   —— ti: 精确、abs: 高精度、cat: 分类限定
# 注意：查询串用「空格分隔的普通表达式」，由 urlencode 统一转义成 arXiv 需要的 + / %22 形式。
# 直接手工拼 `+OR+` 并把裸引号塞进 URL 会得到 InvalidURL / HTTP400。
ARXIV_QUERIES = [
    ("Agent",      'ti:"LLM agent" OR ti:"language model agent" OR ti:"tool use" OR ti:"tool-augmented"'),
    ("Agent",      'abs:"agentic" AND abs:"language model"'),
    ("Token效率",  'ti:"context compression" OR ti:"prompt compression" OR ti:"context caching" OR ti:"KV cache compression"'),
    ("Token效率",  'ti:"token pruning" OR ti:"token efficiency" OR ti:"sparse attention" OR ti:"long context"'),
    ("RAG",        'ti:"retrieval augmented" OR ti:"retrieval-augmented" OR ti:"GraphRAG"'),
    ("代码智能",   'ti:"code generation" OR ti:"code agent" OR ti:"repository level" OR ti:"code intelligence"'),
    ("推理/RL",    'ti:"reasoning" AND ti:"reinforcement learning" AND cat:cs.LG'),
    ("推理/RL",    'ti:"chain-of-thought" OR ti:"test-time compute" OR ti:"process reward"'),
    ("高效推理",   'ti:"quantization" AND ti:"large language model"'),
    ("高效推理",   'ti:"speculative decoding" OR ti:"llm distillation"'),
    ("多模态",     'ti:"vision language model" OR ti:"multimodal large language"'),
    ("聚类/表示",  'ti:"clustering" AND abs:"embedding"'),
    ("记忆",       'ti:"memory" AND ti:"agent" AND cat:cs.AI'),
    ("架构",       'ti:"mixture of experts" OR ti:"state space model"'),
]

# ----------------------------------------------------------------------------- AI 公司博客
# (公司, url, kind)   kind: rss | html
BLOG_SOURCES = [
    ("OpenAI",         "https://openai.com/news/rss.xml",                        "rss"),
    ("Anthropic",      "https://www.anthropic.com/news",                         "html"),
    ("Anthropic Eng",  "https://www.anthropic.com/engineering",                  "html"),
    ("Google DeepMind","https://deepmind.google/blog/rss.xml",                   "rss"),
    ("Google AI Blog", "https://blog.google/technology/ai/rss/",                 "rss"),
    ("Google Research","https://research.google/blog/rss/",                      "rss"),
    ("Meta AI",        "https://ai.meta.com/blog/",                              "html"),
    ("Microsoft Res",  "https://www.microsoft.com/en-us/research/blog/feed/",    "rss"),
    ("NVIDIA",         "https://blogs.nvidia.com/feed/",                         "rss"),
    ("HuggingFace",    "https://hf-mirror.com/blog/feed.xml",                    "rss"),
    ("Mistral",        "https://mistral.ai/news",                                "html"),
    ("AI2",            "https://allenai.org/blog",                               "html"),
    ("Qwen",           "https://qwenlm.github.io/blog/index.xml",                "rss"),
    ("DeepSeek",       "https://api-docs.deepseek.com/news/",                    "html"),
    ("Moonshot",       "https://moonshotai.github.io/",                          "html"),
    ("Zhipu",          "https://zhipuai.cn/news",                                "html"),
    ("Cohere",         "https://cohere.com/blog",                                "html"),
    ("Together",       "https://www.together.ai/blog",                           "html"),
    ("Stability",      "https://stability.ai/news",                              "html"),
    ("ByteDance Seed", "https://seed.bytedance.com/en/blog",                      "html"),
    ("MiniMax",        "https://www.minimaxi.com/news",                          "html"),
    ("Baidu ERNIE",    "https://ernie.baidu.com/blog/",                          "html"),
    ("01.AI",          "https://www.01.ai/",                                     "html"),
    ("OpenRouter",     "https://openrouter.ai/announcements",                    "html"),
]

# 路由记忆：记住哪个源必须走代理，后续运行直接走代理，省掉一次 20s 直连超时。
ROUTES_FILE = BASE / "_routes.json"
ROUTE_CACHE: dict[str, str] = {}


def load_routes():
    global ROUTE_CACHE
    if ROUTES_FILE.exists():
        try:
            ROUTE_CACHE = json.loads(ROUTES_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            ROUTE_CACHE = {}


def save_routes():
    BASE.mkdir(parents=True, exist_ok=True)
    ROUTES_FILE.write_text(json.dumps(ROUTE_CACHE, ensure_ascii=False, indent=1), encoding="utf-8")

# 需要代理的源（直连失败时自动走 SOCKS5）
CODE_HOSTS = ("github.com", "gitlab.com", "codeberg.org", "huggingface.co",
              "huggingface.com", "gitee.com", "bitbucket.org")


# ============================================================================ 网络层
#
# 关键教训：PySocks 的 `socket.socket = socks.socksocket` 是【全局】替换。
# 一旦某个源触发了它，后续所有「直连」请求都会偷偷走代理 —— 本次就因此让
# hf-mirror（实际有 862 条 item）被判定成 "no items".
# 所以这里**不用 PySocks**：直连走 urllib，代理走独立的 curl 子进程，
# 两条路径完全隔离，互不污染。

SOCKS5 = "127.0.0.1:10808"


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def _decode(raw):
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def fetch_direct(url, timeout=20):
    """Direct HTTP via urllib. Never touches any proxy."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/html, */*",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
            return _decode(r.read()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP{e.code}"
    except Exception as e:  # noqa: BLE001
        return None, type(e).__name__


def fetch_via_socks5(url, timeout=25):
    """Isolated proxy fetch through curl --socks5-hostname (no global state)."""
    try:
        p = subprocess.run(
            ["curl", "-sSL", "--socks5-hostname", SOCKS5,
             "--max-time", str(timeout), "-A", UA,
             "-H", "Accept: application/rss+xml, application/atom+xml, text/html, */*",
             url],
            capture_output=True, timeout=timeout + 15,
        )
        if p.returncode != 0 or not p.stdout:
            return None, f"curl_rc{p.returncode}"
        return _decode(p.stdout), None
    except Exception as e:  # noqa: BLE001
        return None, type(e).__name__


def fetch_smart(url, timeout=20, remember=True, retry_429=10):
    """Route-aware fetch. Remembered route first, the other as fallback.

    retry_429: arXiv returns 429 when hit faster than ~1 req/s. When the direct
               attempt is rate-limited, wait and retry direct once before
               falling back to the proxy (the proxy has a different egress IP,
               so it also works, but direct is faster).
    Returns (text, route, err).
    """
    order = ["socks5", "direct"] if ROUTE_CACHE.get(url) == "socks5" else ["direct", "socks5"]
    errs = []
    for route in order:
        if route == "direct":
            txt, err = fetch_direct(url, timeout=timeout)
            if (not txt) and err == "HTTP429" and retry_429:
                time.sleep(retry_429)
                txt, err = fetch_direct(url, timeout=timeout)
        else:
            txt, err = fetch_via_socks5(url, timeout=max(timeout, 25))
        if txt:
            if remember:
                ROUTE_CACHE[url] = route
            return txt, route, None
        errs.append(f"{route}:{err}")
    if remember:
        ROUTE_CACHE.pop(url, None)
    return None, None, " | ".join(errs)


# ============================================================================ 归档 / 去重
def load_seen():
    if ARCHIVE.exists():
        try:
            return json.loads(ARCHIVE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_seen(seen):
    BASE.mkdir(parents=True, exist_ok=True)
    ARCHIVE.write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")


def k_hash(*parts):
    return hashlib.md5("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


# ============================================================================ 通道 1: arXiv
def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def norm_ws(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


_TRAIL_DATE = re.compile(
    r"\s*(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}"
    r"|\d{4}[-/]\d{1,2}[-/]\d{1,2}"
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}"
    r"|\d{1,2}\s+(?:hours?|days?|weeks?|months?|years?)\s+ago)\s*$",
    re.I,
)


def clean_title(s):
    """Strip a trailing date that HTML-embedded titles often carry."""
    return _TRAIL_DATE.sub("", (s or "").strip()).strip(" ·-|")


def find_code_links(text):
    out = []
    for m in re.finditer(r"https?://[^\s,;)\]\"'<>]+", text or ""):
        u = m.group(0).rstrip(".")
        if any(h in u.lower() for h in CODE_HOSTS):
            if u not in out:
                out.append(u)
    return out


OPEN_SRC_SIGNALS = [
    "code is available", "code available", "we release", "we open-source", "open-source",
    "open source", "github.com", "our code", "publicly available", "project page",
    "released at", "released under", "huggingface.co", "models are available",
]


def collect_arxiv(days, seen, verbose=True):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = []
    stats = {"queries": 0, "raw": 0, "kept": 0, "with_code": 0, "errors": []}

    for tag, q in ARXIV_QUERIES:
        # 必须走 urlencode：裸引号/空格直接拼进 URL 会 InvalidURL / HTTP400
        url = "https://export.arxiv.org/api/query?" + urlencode({
            "search_query": q,
            "start": 0,
            "max_results": 40,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        })
        # remember=False: arXiv 每个 query 的 URL 都不同，记路由没意义
        txt, route, err = fetch_smart(url, timeout=25, remember=False)
        stats["queries"] += 1
        if not txt:
            stats["errors"].append(f"arXiv[{tag}] {err}")
            if verbose:
                print(f"  ! arXiv {tag}: {err}", file=sys.stderr)
            continue
        try:
            root = ET.fromstring(txt)
        except ET.ParseError as e:
            stats["errors"].append(f"arXiv[{tag}] parse {e}")
            continue

        got = 0
        for e in root.findall("a:entry", NS):
            raw_id = (e.findtext("a:id", "", NS) or "").strip()
            aid = raw_id.rsplit("/", 1)[-1]
            if not aid:
                continue
            base_id = aid.split("v")[0]
            pub = (e.findtext("a:published", "", NS) or "").strip()
            try:
                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                continue
            if pub_dt < cutoff:
                continue
            stats["raw"] += 1

            title = norm_ws(strip_tags(e.findtext("a:title", "", NS)))
            summary = norm_ws(strip_tags(e.findtext("a:summary", "", NS)))
            comment = norm_ws(strip_tags(e.findtext("arxiv:comment", "", NS)))
            authors = [norm_ws(strip_tags(a.findtext("a:name", "", NS))) for a in e.findall("a:author", NS)]
            cats = [c.get("term", "") for c in e.findall("a:category", NS)]
            blob = f"{title} {summary} {comment}"
            codes = find_code_links(blob)
            hits = [s for s in OPEN_SRC_SIGNALS if s in blob.lower()]

            h = k_hash("arxiv", base_id)
            if h in seen:
                continue
            seen[h] = {"t": datetime.now().isoformat(timespec="seconds"), "kind": "arxiv", "id": base_id}
            got += 1
            stats["kept"] += 1
            if codes:
                stats["with_code"] += 1

            rows.append({
                "type": "arxiv",
                "theme": tag,
                "id": base_id,
                "version": aid,
                "title": title,
                "authors": authors[:6],
                "n_authors": len(authors),
                "published": pub_dt.isoformat(),
                "categories": cats,
                "comment": comment,
                "abstract": summary,
                "code_links": codes,
                "open_source_signals": hits[:4],
                "has_code": bool(codes),
                "abs_url": f"https://arxiv.org/abs/{base_id}",
                "pdf_url": f"https://arxiv.org/pdf/{base_id}",
                "hash": h,
            })
        if verbose:
            print(f"  arXiv {tag:10s} +{got}  (route={route})")
        time.sleep(3.0)  # arXiv 官方建议 ~3s/请求，太密会 429

    return rows, stats


# ============================================================================ 通道 2: 博客
def parse_feed(txt):
    """Generic RSS 2.0 / Atom item extractor -> list of dicts."""
    items = []
    try:
        root = ET.fromstring(txt)
    except ET.ParseError:
        return items

    def txt_of(node, names):
        for n in names:
            v = node.findtext(n)
            if v:
                return norm_ws(strip_tags(v))
        return ""

    # RSS 2.0
    for it in root.iter("item"):
        items.append({
            "title": txt_of(it, ["title"]),
            "link": txt_of(it, ["link"]) or (it.findtext("guid") or "").strip(),
            "date": txt_of(it, ["pubDate", "date", "{http://purl.org/dc/elements/1.1/}date"]),
            "desc": txt_of(it, ["description", "summary"])[:400],
        })
    # Atom
    if not items:
        for it in root.iter("{http://www.w3.org/2005/Atom}entry"):
            link = ""
            for ln in it.findall("{http://www.w3.org/2005/Atom}link"):
                if ln.get("rel") in (None, "alternate"):
                    link = ln.get("href", "")
                    break
            items.append({
                "title": txt_of(it, ["{http://www.w3.org/2005/Atom}title"]),
                "link": link,
                "date": txt_of(it, ["{http://www.w3.org/2005/Atom}updated",
                                    "{http://www.w3.org/2005/Atom}published"]),
                "desc": txt_of(it, ["{http://www.w3.org/2005/Atom}summary",
                                    "{http://www.w3.org/2005/Atom}content"])[:400],
            })
    return [i for i in items if i["title"]]


MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def parse_date_loose(s):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d", "%d %b %Y", "%b %d, %Y", "%Y/%m/%d"):
        try:
            d = datetime.strptime(s.replace("GMT", "+0000").replace("UTC", "+0000"), fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            return None
    return None


def parse_html_items(txt, base_url):
    """Heuristic: pull candidate article links, then try to date them."""
    items = []
    seen_links = set()
    base_origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(base_url))
    for m in re.finditer(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', txt, re.S | re.I):
        href, inner = m.group(1), m.group(2)
        label = clean_title(norm_ws(strip_tags(inner)))
        if not (18 <= len(label) <= 180):
            continue
        if href.startswith("#") or href.startswith("javascript") or href.startswith("mailto"):
            continue
        if any(x in href.lower() for x in ("/tag/", "/category/", "/author/", "/about",
                                           "/careers", "/legal", "/privacy", "/terms",
                                           "/login", "/signup", "/contact", "/pricing",
                                           "/products", "/solutions", "/customers",
                                           "/events", "/cookie", "/rss", "/feed",
                                           "twitter.com", "linkedin.com", "youtube.com",
                                           "facebook.com", "/cdn-cgi/", "/#", ".css", ".js")):
            continue
        # 用 urljoin 正确解析相对路径；手工 base+href 拼接会产生
        # https://site/announcements/blog/announcements/x 这类重复路径。
        if href.startswith("/"):
            href = urljoin(base_origin + "/", href)
        elif href.startswith("http"):
            href = href
        else:
            href = urljoin(base_url, href)
        if not href.startswith("http"):
            continue
        key = href.split("?")[0]
        if key in seen_links:
            continue
        seen_links.add(key)
        # date heuristic: look for a nearby ISO date in the raw html window
        win = txt[max(0, m.start() - 400): m.end() + 400]
        dm = re.search(r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2})", win)
        items.append({
            "title": label,
            "link": href,
            "date": dm.group(1) if dm else "",
            "desc": "",
        })
    # prefer path-depth-1 article-looking links
    items.sort(key=lambda i: (-len([p for p in i["link"].split("/") if p]), len(i["title"])))
    return items[:80]


def collect_blogs(days, seen, verbose=True):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = []
    stats = {"sources": 0, "ok": 0, "items": 0, "dated": 0, "errors": []}

    for company, url, kind in BLOG_SOURCES:
        stats["sources"] += 1
        txt, route, err = fetch_smart(url, timeout=25)
        if not txt:
            stats["errors"].append(f"{company} {err}")
            if verbose:
                print(f"  ! {company}: {err}", file=sys.stderr)
            continue
        items = parse_feed(txt) if kind == "rss" else parse_html_items(txt, url)
        if not items:
            stats["errors"].append(f"{company} no items parsed")
            if verbose:
                print(f"  ! {company}: no items (route={route})", file=sys.stderr)
            continue
        stats["ok"] += 1
        kept = 0
        for it in items:
            dt = parse_date_loose(it.get("date", ""))
            if dt is not None:
                stats["dated"] += 1
                if dt < cutoff:
                    continue
            link = (it.get("link") or "").split("?")[0]
            if not link:
                continue
            h = k_hash("blog", company, link)
            if h in seen:
                continue
            seen[h] = {"t": datetime.now().isoformat(timespec="seconds"), "kind": "blog", "company": company}
            kept += 1
            stats["items"] += 1
            rows.append({
                "type": "blog",
                "company": company,
                "title": clean_title(it["title"]),
                "link": link,
                "date": dt.isoformat() if dt else it.get("date", ""),
                "date_known": dt is not None,
                "desc": it.get("desc", ""),
                "source_route": route,
                "hash": h,
            })
        if verbose:
            print(f"  {company:16s} +{kept:<3} route={route} kind={kind}")
    return rows, stats


# ============================================================================ 输出
def write_outputs(papers, blogs, days):
    BASE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    day = datetime.now().strftime("%Y-%m-%d")

    pj = BASE / f"{stamp}_arxiv_opensource.jsonl"
    bj = BASE / f"{stamp}_blogs.jsonl"
    md = BASE / f"{stamp}_digest.md"

    with pj.open("w", encoding="utf-8") as f:
        for r in papers:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with bj.open("w", encoding="utf-8") as f:
        for r in blogs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    L = []
    L.append(f"# AI 前沿采集摘要 — {day}（最近 {days} 天）\n")
    L.append(f"- arXiv 论文：**{len(papers)}** 篇（其中标注到开源代码 **{sum(1 for p in papers if p['has_code'])}** 篇）")
    L.append(f"- AI 公司博客：**{len(blogs)}** 条，覆盖 {len(set(b['company'] for b in blogs))} 家")
    L.append("")

    if papers:
        L.append("## 一、arXiv 开源论文\n")
        by_code = [p for p in papers if p["has_code"]]
        others = [p for p in papers if not p["has_code"]]
        if by_code:
            L.append(f"### 1.1 带开源代码（{len(by_code)} 篇）\n")
            for p in sorted(by_code, key=lambda x: x["published"], reverse=True):
                L.append(f"- **{p['title']}**")
                L.append(f"  - `{p['id']}` · {p['published'][:10]} · 主题:{p['theme']} · {p['categories'][:3]}")
                L.append(f"  - 代码: {' '.join(p['code_links'][:2])}")
                if p["open_source_signals"]:
                    L.append(f"  - 开源信号: {', '.join(p['open_source_signals'])}")
                L.append(f"  - 摘要: {p['abstract'][:280]}…")
                L.append("")
        if others:
            L.append(f"### 1.2 其余（{len(others)} 篇，未在摘要中标注代码）\n")
            for p in sorted(others, key=lambda x: x["published"], reverse=True):
                L.append(f"- **{p['title']}**")
                L.append(f"  - `{p['id']}` · {p['published'][:10]} · 主题:{p['theme']}")
                L.append(f"  - {p['abs_url']}")
                L.append("")
    if blogs:
        L.append("## 二、AI 公司博客\n")
        for comp in dict.fromkeys(b["company"] for b in blogs):
            group = [b for b in blogs if b["company"] == comp]
            L.append(f"### {comp}（{len(group)}）")
            for b in group:
                dtxt = b["date"][:10] if b["date_known"] else "(站内未给日期)"
                L.append(f"- [{b['title']}]({b['link']}) · {dtxt}")
            L.append("")
    md.write_text("\n".join(L), encoding="utf-8")
    return pj, bj, md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--papers-only", action="store_true")
    ap.add_argument("--blogs-only", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    t0 = time.time()
    seen = load_seen()
    load_routes()
    papers, blogs = [], []

    if not a.blogs_only:
        print(f"[1/2] arXiv 开源论文（最近 {a.days} 天，{len(ARXIV_QUERIES)} 个主题查询）")
        papers, ps = collect_arxiv(a.days, seen, verbose=not a.quiet)
        print(f"      -> {len(papers)} 篇（原始命中 {ps['raw']}，带代码 {ps['with_code']}）")
    if not a.papers_only:
        print(f"[2/2] AI 公司博客（{len(BLOG_SOURCES)} 个源）")
        blogs, bs = collect_blogs(a.days, seen, verbose=not a.quiet)
        print(f"      -> {len(blogs)} 条（成功源 {bs['ok']}/{bs['sources']}）")

    save_seen(seen)
    save_routes()
    pj, bj, md = write_outputs(papers, blogs, a.days)
    print(f"\n归档:\n  {pj}\n  {bj}\n  摘要: {md}\n耗时 {round(time.time()-t0,1)}s")

    if not a.quiet:
        print("\n" + "=" * 78)
        print(md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
