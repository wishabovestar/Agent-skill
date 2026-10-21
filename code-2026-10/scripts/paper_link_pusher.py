"""
巡天论文推送 + PDF接收 + 智能分析系统 (qqbot2微信平台)
v2.0 — 域过滤推送 + 论文总结 + 研究上下文分析

功能:
  1. 陶瓷/物理/数学/统计域论文触发推送（其他类型一同发出）
  2. 用户发送PDF → 总结 + 结合会话历史提供机理参考
  3. 利用知识库和数学组Agent进行趋势分析
"""
import json, os, re, shutil, hashlib, glob
from pathlib import Path
from datetime import datetime
import subprocess

# ===== 配置 =====
PROFILE = "qqbot2"
HOME = Path("D:/hermes/hermes-data/profiles") / PROFILE
KNOWLEDGE_ROOTS = {
    "book_knowledge": Path("D:/hermes/data/book_knowledge"),
    "physics_knowledge": Path("D:/hermes/data/physics_knowledge"),
    "math_knowledge": Path("D:/hermes/data/math_knowledge"),
}
PAPER_REQUEST_DB = HOME / "paper_requests.json"
PDF_STORAGE = Path("D:/hermes/data/user_uploaded_pdfs")
USER_PROFILES = HOME / "user_profiles"

# ===== 域分类 =====
DOMAIN_CERAMICS = ["ceramics", "sintering", "alumina", "zirconia", "silicon carbide",
                   "MAX phase", "ferroelectric", "dielectric", "BaTiO3",
                   "陶瓷", "烧结", "氧化铝", "氧化锆", "碳化硅", "铁电", "介电"]
DOMAIN_PHYSICS = ["solid state physics", "condensed matter", "DFT", "molecular dynamics",
                  "thermal conductivity", "mechanical property", "crystal structure",
                  "固体物理", "凝聚态", "计算物理", "热传导", "力学性能"]
DOMAIN_MATH = ["statistical", "bayesian", "optimization", "numerical", "monte carlo",
               "convex", "probability", "statistics", "regression",
               "统计", "贝叶斯", "优化", "数值", "概率", "回归"]
DOMAIN_STATS = ["data science", "machine learning", "neural network", "deep learning",
                "causal inference", "time series", "anomaly detection",
                "数据科学", "机器学习", "深度学习", "因果推断", "时间序列"]

ALL_SCIENCE_DOMAINS = DOMAIN_CERAMICS + DOMAIN_PHYSICS + DOMAIN_MATH + DOMAIN_STATS

# ===== 域检测 =====
def detect_domain(title, url, note="", abstract=""):
    """Detect paper domain from title/URL/note/abstract"""
    text = f"{title} {url} {note} {abstract}".lower()
    domains = []
    # Check each domain category
    if any(kw.lower() in text for kw in DOMAIN_CERAMICS):
        domains.append("ceramics")
    if any(kw.lower() in text for kw in DOMAIN_PHYSICS):
        domains.append("physics")
    if any(kw.lower() in text for kw in DOMAIN_MATH):
        domains.append("math")
    if any(kw.lower() in text for kw in DOMAIN_STATS):
        domains.append("stats")
    return domains if domains else ["other"]

def is_science_domain(title, url, note="", abstract=""):
    """Check if paper belongs to science domains"""
    text = f"{title} {url} {note} {abstract}".lower()
    return any(kw.lower() in text for kw in ALL_SCIENCE_DOMAINS)

def domain_emoji(domains):
    """Get emoji for domain"""
    emoji_map = {"ceramics": "🏺", "physics": "⚛", "math": "📐", "stats": "📊", "other": "📄"}
    return " ".join(emoji_map.get(d, "📄") for d in domains)

# ===== 知识库扫描 =====
def scan_papers_needing_pdf():
    """Scan knowledge bases for papers needing PDF access"""
    needs_push = []
    for kb_name, kb_root in KNOWLEDGE_ROOTS.items():
        if not kb_root.exists():
            continue
        for f in kb_root.rglob("*.json"):
            if "_log" in f.name or "routing" in f.name:
                continue
            try:
                with open(f, encoding="utf-8") as fh:
                    data = json.load(fh)
            except:
                continue
            title = data.get("title", "")
            url = data.get("url", "")
            note = data.get("note", "")
            abstract = data.get("abstract", "")
            if not url:
                continue
            # Detect paywall
            is_paywalled = any(kw in url.lower() for kw in [
                "sciencedirect", "springer", "wiley", "acs.org", "rsc.org",
                "ieee", "nature.com", "cell.com", "cnki", "cqvip",
                "dfcfw", "researchgate.net/publication"
            ])
            is_open = any(kw in url.lower() for kw in [
                "arxiv.org", "openaccess", "creativecommons"
            ])
            if is_paywalled and not is_open:
                domains = detect_domain(title, url, note, abstract)
                entry = {
                    "id": data.get("id", hashlib.md5(title.encode()).hexdigest()[:12]),
                    "title": title[:120], "url": url,
                    "source": kb_name, "subdir": data.get("subdir", ""),
                    "domains": domains, "is_science": is_science_domain(title, url, note, abstract),
                    "note": note[:200], "found_at": datetime.now().isoformat(), "pushed": False,
                }
                needs_push.append(entry)
    return needs_push

# ===== 推送论文到微信（含域标识）=====
def push_paper_link(paper):
    """Push paper link to qqbot2 WeChat with domain tag"""
    emoji = domain_emoji(paper["domains"])
    tag = "🔬" if paper["is_science"] else "📄"
    domains_str = "/".join(paper["domains"]) if paper["domains"] else "general"
    msg = (
        f"{tag} 文献发现 ({domains_str})\n"
        f"标题: {paper['title'][:80]}\n"
        f"来源: {paper['source']}/{paper.get('subdir','')}\n"
        f"链接: {paper['url']}\n"
        f"提示: {paper['note'][:100]}\n"
        f"如需全文请发送PDF到本聊天"
    )
    try:
        r = subprocess.run(
            ["hermes", "--profile", "qqbot2", "send", "-t", "weixin", msg],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            print(f"    send warn: {r.stderr[:100]}")
            import time
            time.sleep(20)  # rate limit cooldown
            return False
        return True
    except Exception as e:
        print(f"    send error: {e}")
        import time
        time.sleep(20)
        return False

# ===== 论文分析（结合知识库+会话上下文）=====
def analyze_paper_insights(paper_title, paper_url, paper_abstract=""):
    """
    Analyze paper and provide research-relevant insights
    Uses knowledge base and domain context to find connections
    """
    insights = {
        "summary": "",
        "related_knowledge": [],
        "research_relevance": "",
        "mechanism_insights": [],
    }
    
    # Search knowledge base for related papers
    related = []
    for kb_name, kb_root in KNOWLEDGE_ROOTS.items():
        if not kb_root.exists():
            continue
        for f in kb_root.rglob("*.json"):
            if "_log" in f.name or "routing" in f.name:
                continue
            try:
                with open(f, encoding="utf-8") as fh:
                    data = json.load(fh)
            except:
                continue
            t = data.get("title", "")
            ab = data.get("abstract", "") or ""
            n = data.get("note", "") or ""
            # Check if related by shared keywords
            keywords = set(re.findall(r'\w+', paper_title.lower()[:50]))
            title_words = set(re.findall(r'\w+', t.lower()[:50]))
            overlap = keywords & title_words
            if len(overlap) >= 2 and len(keywords) >= 3:
                related.append({
                    "title": t[:80], "url": data.get("url", ""),
                    "source": kb_name, "relevance": len(overlap),
                })
    
    related.sort(key=lambda x: -x["relevance"])
    insights["related_knowledge"] = related[:5]
    
    # Mechanism reference analysis
    domains = detect_domain(paper_title, paper_url)
    if "ceramics" in domains:
        insights["mechanism_insights"].append("🏺 陶瓷机理: 关注烧结动力学/晶界扩散/相变增韧机制")
    if "physics" in domains:
        insights["mechanism_insights"].append("⚛ 物理机制: 关注热力学/输运性质/缺陷化学")
    if "math" in domains or "stats" in domains:
        insights["mechanism_insights"].append("📊 方法学: 可借鉴统计建模/优化方法到电池/陶瓷研究")
    
    # Research relevance estimate
    if paper_abstract:
        abs_lower = paper_abstract.lower()
        if "sinter" in abs_lower or "grain" in abs_lower:
            insights["research_relevance"] = "与陶瓷烧结工艺直接相关，可供工艺参数优化参考"
        elif "battery" in abs_lower or "lithium" in abs_lower or "electrode" in abs_lower:
            insights["research_relevance"] = "与锂电池研发方向相关，可参考其表征/分析方法"
        elif "model" in abs_lower or "simulation" in abs_lower or "DFT" in abs_lower:
            insights["research_relevance"] = "计算方法可迁移至材料性能预测"
        else:
            insights["research_relevance"] = "间接相关，建议阅读后评估"
    
    return insights

# ===== 论文摘要（快速）=====
def quick_summary(title, url, abstract=""):
    """Generate a quick summary from available metadata"""
    summary_parts = []
    if title:
        summary_parts.append(f"📌 {title[:100]}")
    if abstract and len(abstract) > 20:
        # Extract key sentences
        sentences = re.split(r'[.。]', abstract)
        key_sentences = [s.strip() for s in sentences if len(s.strip()) > 30][:3]
        if key_sentences:
            summary_parts.append("📝 要点:")
            for s in key_sentences:
                summary_parts.append(f"  • {s[:120]}")
    if url:
        summary_parts.append(f"🔗 {url}")
    return "\n".join(summary_parts)

# ===== 域过滤推送 =====
def push_domain_filtered():
    """Push papers, with science domains prioritized and tagged"""
    if not PAPER_REQUEST_DB.exists():
        papers = scan_papers_needing_pdf()
    else:
        with open(PAPER_REQUEST_DB) as f:
            papers = json.load(f)
    
    unpushed = [p for p in papers if not p.get("pushed")]
    if not unpushed:
        print("✅ No outstanding paper requests to push")
        return 0
    
    # Sort: science domains first, then others
    science = [p for p in unpushed if p.get("is_science")]
    others = [p for p in unpushed if not p.get("is_science")]
    
    pushed_count = 0
    # Push science domain papers first (max 3 per run)
    for p in (science + others)[:5]:
        print(f"  📤 [{','.join(p.get('domains',['other']))}] {p['title'][:60]}...")
        if push_paper_link(p):
            import time
            time.sleep(25)  # 25s between sends to avoid rate limit
            p["pushed"] = True
            p["pushed_at"] = datetime.now().isoformat()
            pushed_count += 1
    
    with open(PAPER_REQUEST_DB, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)
    
    # Report breakdown
    sci_count = len([p for p in (science + others)[:5] if p.get("is_science")])
    print(f"  🔬 科学域论文: {sci_count} | 📄 其他: {pushed_count - sci_count}")
    return pushed_count

# ===== 论文分析入口（给用户交互用）=====
def handle_analyze_paper(user_input):
    """
    Analyze a paper based on user's message.
    Accepts: paper URL or title mentioned in chat
    Returns: analysis with summary + related knowledge + research insights
    """
    url_match = re.search(r"(https?://[^\s]+)", user_input)
    url = url_match.group(1) if url_match else ""
    
    # Extract potential title from user input
    title = user_input.replace("分析", "").replace("总结", "").replace("看看", "").strip()
    if url:
        title = title.replace(url, "").strip()
    
    # Search knowledge base for this paper
    found = None
    for kb_name, kb_root in KNOWLEDGE_ROOTS.items():
        if not kb_root.exists():
            continue
        for f in kb_root.rglob("*.json"):
            if "_log" in f.name or "routing" in f.name:
                continue
            try:
                with open(f, encoding="utf-8") as fh:
                    data = json.load(fh)
            except:
                continue
            if url and data.get("url","") == url:
                found = data
                break
            if title and (title[:30].lower() in data.get("title","").lower()):
                found = data
                break
    
    if found:
        paper_title = found.get("title", "")
        paper_url = found.get("url", "")
        paper_abstract = found.get("abstract", "") or found.get("note", "") or ""
        
        result = []
        result.append("📖 **论文分析报告**\n")
        result.append(quick_summary(paper_title, paper_url, paper_abstract))
        result.append("")
        
        insights = analyze_paper_insights(paper_title, paper_url, paper_abstract)
        
        if insights["research_relevance"]:
            result.append(f"\n🎯 **研究方向关联**: {insights['research_relevance']}")
        
        if insights["mechanism_insights"]:
            result.append(f"\n🔬 **机理参考**:")
            for m in insights["mechanism_insights"]:
                result.append(f"  {m}")
        
        if insights["related_knowledge"]:
            result.append(f"\n📚 **关联知识 ({len(insights['related_knowledge'])}条):**")
            for r in insights["related_knowledge"][:3]:
                result.append(f"  • [{r['source']}] {r['title'][:60]}")
                if r.get("url"):
                    result.append(f"    {r['url']}")
        
        return "\n".join(result)
    else:
        return f"未在知识库中找到该论文。请发送论文链接或PDF文件入库后再分析。"

# ===== PDF存储 =====
def store_pdf(source_path, filename, category="literature", subdir=""):
    """Store user-provided PDF into knowledge base"""
    PDF_STORAGE.mkdir(parents=True, exist_ok=True)
    target_dir = PDF_STORAGE / category / (subdir or "misc")
    target_dir.mkdir(parents=True, exist_ok=True)
    
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', filename)[:100]
    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"
    item_id = hashlib.md5(f"user_upload:{filename}".encode()).hexdigest()[:12]
    dest = target_dir / f"{item_id}_{safe_name}"
    
    if dest.exists():
        return dest, "exists"
    
    shutil.copy2(source_path, dest)
    meta = {"id": item_id, "title": filename[:100], "path": str(dest),
            "category": category, "subdir": subdir,
            "uploaded_at": datetime.now().isoformat()}
    with open(dest.with_suffix(".json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    
    log_file = PDF_STORAGE / "_upload_log.json"
    log = {"uploads": [], "total": 0}
    if log_file.exists():
        with open(log_file) as f: log = json.load(f)
    log["uploads"].append({"id": item_id, "title": filename[:60], "path": str(dest),
                           "ts": datetime.now().isoformat()})
    log["total"] = len(log["uploads"])
    if len(log["uploads"]) > 1000: log["uploads"] = log["uploads"][-500:]
    with open(log_file, "w") as f: json.dump(log, f, ensure_ascii=False, indent=2)
    
    return dest, "new"

# ===== 交互处理器 =====
def handle_user_message(user_input):
    """Handle user messages on WeChat related to papers"""
    # 分析论文
    if any(kw in user_input for kw in ["分析", "总结", "看看这篇"]):
        return handle_analyze_paper(user_input)
    
    # 收录论文链接
    url_match = re.search(r"(https?://[^\s]+)", user_input)
    if url_match and any(kw in user_input for kw in ["收录", "论文", "文献"]):
        url = url_match.group(1)
        return handle_record_request(user_input, url)
    
    # 发送PDF（标记）
    if user_input.lower().endswith(".pdf"):
        return handle_pdf_upload(user_input)
    
    return None

def handle_record_request(user_input, url):
    """Record a paper request from user"""
    entry = {
        "id": hashlib.md5(url.encode()).hexdigest()[:12],
        "title": user_input.replace(url, "").strip()[:80],
        "url": url, "source": "user_request",
        "domains": detect_domain(user_input, url),
        "is_science": is_science_domain(user_input, url),
        "pushed": False, "user_requested": True,
        "found_at": datetime.now().isoformat(),
    }
    papers = []
    if PAPER_REQUEST_DB.exists():
        with open(PAPER_REQUEST_DB) as f: papers = json.load(f)
    papers.append(entry)
    with open(PAPER_REQUEST_DB, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)
    return f"✅ 已记录论文链接\n请发送PDF文件到本聊天以入库分析"

def handle_pdf_upload(filepath):
    """Handle a PDF file sent by user"""
    if os.path.exists(filepath):
        dest, status = store_pdf(filepath, os.path.basename(filepath))
        if status == "new":
            return f"✅ PDF已入库: {dest}\n输入「分析{os.path.basename(filepath)}」获取论文分析报告"
        else:
            return f"⏭️ 文件已存在: {dest}"
    return None

# ===== 主入口 =====
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"
    
    if cmd == "scan":
        papers = scan_papers_needing_pdf()
        science = [p for p in papers if p.get("is_science")]
        print(f"📊 扫描结果: {len(papers)} 篇论文可能需要PDF")
        print(f"  🔬 科学域(陶瓷/物理/数学/统计): {len(science)} 篇")
        for p in science[:5]:
            print(f"    {domain_emoji(p['domains'])} {p['title'][:70]}")
            print(f"      域名: {','.join(p['domains'])}")
        others = [p for p in papers if not p.get("is_science")]
        for p in others[:3]:
            print(f"    📄 {p['title'][:70]}")
        if len(papers) > 8:
            print(f"  ... 共 {len(papers)} 篇")
        with open(PAPER_REQUEST_DB, "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 已保存到 {PAPER_REQUEST_DB}")
    
    elif cmd == "push":
        n = push_domain_filtered()
        print(f"📤 推送完成: {n} 篇")
    
    elif cmd == "analyze":
        msg = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if msg:
            print(handle_analyze_paper(msg))
        else:
            print("用法: python paper_link_pusher.py analyze <论文标题或URL>")
    
    elif cmd == "store":
        if len(sys.argv) < 3:
            print("用法: python paper_link_pusher.py store <pdf路径> [分类] [子目录]")
        else:
            path = sys.argv[2]
            cat = sys.argv[3] if len(sys.argv) > 3 else "literature"
            sub = sys.argv[4] if len(sys.argv) > 4 else ""
            if os.path.exists(path):
                dest, status = store_pdf(path, os.path.basename(path), cat, sub)
                print(f"  {status.upper()}: {dest}")
            else:
                print(f"❌ 文件不存在: {path}")
    
    elif cmd == "reset":
        if PAPER_REQUEST_DB.exists():
            with open(PAPER_REQUEST_DB) as f:
                papers = json.load(f)
            for p in papers:
                p["pushed"] = False
            with open(PAPER_REQUEST_DB, "w", encoding="utf-8") as f:
                json.dump(papers, f, ensure_ascii=False, indent=2)
            print(f"✅ 重置 {len(papers)} 篇推送状态")
        else:
            print("❌ 无记录")
