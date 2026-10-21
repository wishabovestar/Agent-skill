"""
巡天教材/文献/报告/图灵系列采集器 v1.0
新增4类知识源：
  1. 教材(Textbooks) — 专业教材/经典著作
  2. 文献(Literature) — 学术论文/综述/学位论文
  3. 报告(Reports) — 行业报告/白皮书/券商研报
  4. 图灵系列(Turing) — 人民邮电出版社图灵系列图书
"""
import json, os, re, time, hashlib
from pathlib import Path
from datetime import datetime

# ===== 目录结构 =====
DATA_ROOT = Path("D:/hermes/data")
BOOK_DIR = DATA_ROOT / "book_knowledge"       # 新目录：教材/文献/报告/图灵
COLLECT_LOG = BOOK_DIR / "_collection_log.json"

# ===== 知识源类型定义 =====
KNOWLEDGE_SOURCES = {
    "textbook": {
        "label": "教材(Textbook)",
        "dir": "textbooks",
        "description": "专业教学用书、经典教材",
        "subdirs": {
            "battery": "电池/电化学",
            "materials": "材料科学",
            "ai_ml": "人工智能/机器学习",
            "programming": "编程/算法",
            "math": "数学/统计",
            "physics": "物理/工程",
        }
    },
    "literature": {
        "label": "文献(Literature)",
        "dir": "literature",
        "description": "学术论文、综述、学位论文、技术报告",
        "subdirs": {
            "prelithiation_review": "预锂化综述",
            "prelithiation_paper": "预锂化研究论文",
            "anode_silicon": "硅负极/高容量负极",
            "cathode_lco": "正极补锂/LCO",
            "battery_aging": "电池老化/寿命",
            "electrolyte": "电解液/界面",
        }
    },
    "report": {
        "label": "报告(Report)",
        "dir": "reports",
        "description": "行业报告、白皮书、券商研报、技术路线图",
        "subdirs": {
            "industry": "行业研究报告",
            "broker": "券商研报",
            "whitepaper": "企业白皮书",
            "roadmap": "技术路线图",
            "patent": "专利分析",
        }
    },
    "turing": {
        "label": "图灵系列(Turing)",
        "dir": "turing",
        "description": "人民邮电出版社图灵系列经典图书",
        "subdirs": {
            "computer_science": "计算机科学",
            "programming": "程序设计",
            "ai_ml": "人工智能/机器学习",
            "math_stats": "数学/统计学",
            "electronics": "电子/电气工程",
        }
    }
}

# ===== 预定义采集目标 =====
COLLECTION_RULES = {
    "textbook": {
        "battery": {
            "keywords": [
                "锂离子电池 教材", "电化学 原理 教材", "battery textbook",
                "lithium battery book", "electrochemistry textbook",
                "电池技术 教材", "锂离子电池 制造 工艺"
            ],
            "priority": "P0",
            "interval_hours": 168,  # 每周
        },
        "materials": {
            "keywords": ["材料科学 教材", "materials science textbook"],
            "priority": "P1",
            "interval_hours": 336,
        },
        "ai_ml": {
            "keywords": [
                "deep learning book", "machine learning textbook",
                "PRML book", "统计学习方法 教材"
            ],
            "priority": "P1",
            "interval_hours": 336,
        }
    },
    "literature": {
        "prelithiation_review": {
            "keywords": [
                "pre-lithiation review", "prelithiation review 2024 2025",
                "预锂化 综述", "补锂技术 综述", "lithium prelithiation methods",
                "预锂化 研究进展 2025", "prelithiation strategies review"
            ],
            "priority": "P0",
            "interval_hours": 48,
        },
        "prelithiation_paper": {
            "keywords": [
                "lithium prelithiation paper", "prelithiation silicon anode",
                "正极补锂 Li5FeO4", "prelithiation cathode additive",
                "roll-to-roll prelithiation", "electrochemical prelithiation",
                "预锂化 硅负极", "补锂剂 研究"
            ],
            "priority": "P0",
            "interval_hours": 72,
        },
        "anode_silicon": {
            "keywords": [
                "silicon anode review 2024", "Si-C composite anode",
                "硅负极 研究进展", "high capacity anode prelithiation",
                "silicon oxide anode"
            ],
            "priority": "P1",
            "interval_hours": 96,
        },
        "cathode_lco": {
            "keywords": [
                "LCO cathode prelithiation", "Li-rich cathode review",
                "正极补锂 富锂", "overlithiated cathode",
                "Li5FeO4 cathode additive"
            ],
            "priority": "P1",
            "interval_hours": 96,
        }
    },
    "report": {
        "industry": {
            "keywords": [
                "锂电池行业报告 2024 2025", "锂电产业白皮书",
                "battery industry report", "lithium battery market report",
                "预锂化 行业 报告", "电池补锂 产业 报告"
            ],
            "priority": "P0",
            "interval_hours": 168,  # 每周
        },
        "broker": {
            "keywords": [
                "预锂化 研报", "锂电池 补锂 券商", "battery pre-lithiation research report",
                "电池科技前瞻 报告", "锂电 新技术 研报", "硅负极 研报"
            ],
            "priority": "P0",
            "interval_hours": 72,
        },
        "whitepaper": {
            "keywords": [
                "battery whitepaper", "锂电池白皮书",
                "electric vehicle battery report", "energy storage white paper",
                "储能白皮书", "动力电池白皮书"
            ],
            "priority": "P1",
            "interval_hours": 336,
        },
        "roadmap": {
            "keywords": [
                "battery technology roadmap", "锂电技术路线图",
                "lithium battery roadmap 2025", "all-solid-state roadmap",
                "中国锂电 发展路线图"
            ],
            "priority": "P1",
            "interval_hours": 336,
        }
    },
    "turing": {
        "computer_science": {
            "keywords": [
                "图灵 计算机科学 丛书", "计算机程序的构造和解释 SICP",
                "算法导论 CLRS", "计算机系统结构 图灵",
                "图灵 计算机 经典 图书", "计算机科学 基础 图灵"
            ],
            "priority": "P1",
            "interval_hours": 336,
        },
        "programming": {
            "keywords": [
                "图灵 程序设计 丛书", "Python 编程 从入门到实践",
                "图灵 编程 经典", "程序员 修炼 之道",
                "代码整洁之道", "设计模式 图灵"
            ],
            "priority": "P1",
            "interval_hours": 336,
        },
        "ai_ml": {
            "keywords": [
                "图灵 人工智能 丛书", "深度学习 花书",
                "机器学习 西瓜书", "模式识别与机器学习 PRML",
                "统计学习导论 ISLR", "hands-on machine learning",
                "reinforcement learning book", "deep learning turing series"
            ],
            "priority": "P0",
            "interval_hours": 168,  # 每周 — 高频关注
        },
        "math_stats": {
            "keywords": [
                "图灵 数学 统计 丛书", "概率论 数理统计 教材",
                "线性代数 图灵", "numerical recipes",
                "凸优化 Boyd", "统计学习方法 李航"
            ],
            "priority": "P1",
            "interval_hours": 336,
        },
        "electronics": {
            "keywords": [
                "图灵 电子 电气 工程", "电路 教材 图灵",
                "信号与系统 图灵", "数字信号处理 图灵"
            ],
            "priority": "P2",
            "interval_hours": 720,
        }
    }
}

# ===== 图灵系列已知经典书单 =====
TURING_CLASSICS = {
    "computer_science": [
        {"title": "计算机程序的构造和解释(SICP)", "author": "Harold Abelson",
         "press": "人民邮电出版社", "isbn": "9787115481001", "year": 2019,
         "url": "https://www.ituring.com.cn/book/1"},
        {"title": "算法导论(CLRS 4th)", "author": "Thomas H. Cormen",
         "press": "人民邮电出版社", "isbn": "9787115598075", "year": 2023,
         "url": "https://www.ituring.com.cn/book/2926"},
        {"title": "计算机系统概论", "author": "Yale N. Patt",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/20"},
        {"title": "深入理解计算机系统(CS:APP)", "author": "Randal E. Bryant",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/2483"},
        {"title": "编程珠玑", "author": "Jon Bentley",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/110"},
        {"title": "具体数学", "author": "Ronald L. Graham",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/9"},
    ],
    "programming": [
        {"title": "Python编程从入门到实践(第3版)", "author": "Eric Matthes",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/3172"},
        {"title": "代码整洁之道", "author": "Robert C. Martin",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/100"},
        {"title": "程序员修炼之道(第2版)", "author": "David Thomas",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/2732"},
        {"title": "设计模式", "author": "Erich Gamma",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/99"},
        {"title": "重构：改善既有代码的设计", "author": "Martin Fowler",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/97"},
    ],
    "ai_ml": [
        {"title": "深度学习(花书)", "author": "Ian Goodfellow",
         "press": "人民邮电出版社", "isbn": "9787115467159",
         "url": "https://www.ituring.com.cn/book/2150"},
        {"title": "机器学习(西瓜书)", "author": "周志华",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/1760"},
        {"title": "模式识别与机器学习(PRML)", "author": "Christopher Bishop",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/123"},
        {"title": "统计学习导论(ISLR)", "author": "Gareth James",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/2491"},
        {"title": "强化学习导论(Sutton)", "author": "Richard S. Sutton",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/1733"},
        {"title": "动手学深度学习(PyTorch版)", "author": "阿斯顿·张",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/2707"},
        {"title": "统计学习方法(第2版)", "author": "李航",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/2656"},
        {"title": "机器学习实战", "author": "Peter Harrington",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/144"},
    ],
    "math_stats": [
        {"title": "概率论与数理统计", "author": "William Feller",
         "press": "人民邮电出版社", "url": ""},
        {"title": "线性代数及其应用", "author": "Gilbert Strang",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/20"},
        {"title": "Numerical Recipes数值 recipes", "author": "William H. Press",
         "press": "人民邮电出版社", "url": ""},
        {"title": "凸优化", "author": "Stephen Boyd",
         "press": "人民邮电出版社", "url": "https://www.ituring.com.cn/book/1529"},
    ],
    "electronics": [
        {"title": "信号与系统", "author": "Alan V. Oppenheim",
         "press": "人民邮电出版社", "url": ""},
        {"title": "数字信号处理", "author": "Alan V. Oppenheim",
         "press": "人民邮电出版社", "url": ""},
    ]
}

# ===== 已搜索到的论文/文献/报告索引 =====
KNOWN_LITERATURE = [
    # === 预锂化综述(2024-2025最新) ===
    {"type": "literature", "subdir": "prelithiation_review",
     "title": "锂离子电池预锂化技术研究进展",
     "source": "中国期刊网", "url": "https://www.jfmd.net.cn/cn/article/pdf/preview/10.20027/jfmd.2603038.pdf",
     "year": 2026, "note": "2026年最新综述 — SEI膜/首效/硅负极"},
    {"type": "literature", "subdir": "prelithiation_review",
     "title": "锂离子电池补锂技术(田孟羽等)",
     "source": "储能科学与技术", "url": "https://esst.cip.com.cn/article/2021/2095-4239/2095-4239-2021-10-3-800.shtml",
     "year": 2021, "note": "经典补锂综述，被引7次"},
    {"type": "literature", "subdir": "prelithiation_review",
     "title": "锂离子电池预锂化补锂策略研究进展(宗菲菲等)",
     "source": "化学通报", "url": "http://cnjournals.com/view_abstract.aspx?aid=C09695B7678864E4F7154A8E5D86E6DC&jid=993026051B0258CF7D678808088F34B2",
     "year": 2023, "note": "全面综述预锂化策略"},
    {"type": "literature", "subdir": "prelithiation_review",
     "title": "锂电池预锂化研究进展(2026)",
     "source": "动力与燃料电池", "url": "http://www.pfoc.org.cn/OA/pdfdow.aspx?Sid=20260401",
     "year": 2026, "note": "2026年最新预锂化综述"},   
    # === 预锂化研究论文 ===
    {"type": "literature", "subdir": "prelithiation_paper",
     "title": "Preparation and electrochemical properties of high-stability cathode prelithiation materials",
     "source": "中国化学学报", "url": "http://www.ccspublishing.org.cn/article/doi/10.11862/CJIC.20240441",
     "year": 2025, "note": "高稳定性正极补锂材料"},
    {"type": "literature", "subdir": "prelithiation_paper",
     "title": "Prelithiation Enhances Cycling Life of Lithium-Ion Batteries",
     "source": "电化学(中英文)", "url": "http://dianda.cqvip.com/Qikan/Article/Detail?id=00004G0D477NFHCJNX8G7JP0MJDO3JP1MNR",
     "year": 2025, "note": "预锂化提升循环寿命"},
    {"type": "literature", "subdir": "prelithiation_paper",
     "title": "锂离子电池新型正极补锂剂材料设计(乔羽课题组)",
     "source": "厦门大学", "url": "https://chem.xmu.edu.cn/info/1274/119945.htm",
     "year": 2025, "note": "乔羽课题组富锂层状氧化物补锂剂"},
    {"type": "literature", "subdir": "prelithiation_paper",
     "title": "高容量锂离子电池正极补锂材料Li5FeO4@C的性能研究",
     "source": "储能科学与技术", "url": "https://esst.cip.com.cn/CN/abstract/abstract1431.shtml",
     "year": 2025, "note": "Li5FeO4@C正极补锂材料"},
    # === 报告 ===
    {"type": "report", "subdir": "broker",
     "title": "电池科技前瞻系列报告之二十：预锂化",
     "source": "东方财富", "url": "https://pdf.dfcfw.com/pdf/H3_AP202203151552781191_1.pdf?1647359996000.pdf",
     "year": 2022, "note": "券商研报：预锂化使首效72%→近100%"},
    {"type": "report", "subdir": "industry",
     "title": "Research Progress on Key Materials and Technologies for Secondary Batteries",
     "source": "ResearchGate", "url": "https://www.researchgate.net/publication/364257989_Research_Progress_on_Key_Materials_and_Technologies_for_Secondary_Batteries",
     "year": 2022, "note": "二次电池关键材料综述，含多类电池体系"},
]


# ===== 核心函数 =====
def init():
    """初始化所有目录"""
    for source_type, info in KNOWLEDGE_SOURCES.items():
        base_dir = BOOK_DIR / info["dir"]
        base_dir.mkdir(parents=True, exist_ok=True)
        for subdir_name in info["subdirs"]:
            sub_path = base_dir / subdir_name
            sub_path.mkdir(parents=True, exist_ok=True)
    if not COLLECT_LOG.exists():
        with open(COLLECT_LOG, "w") as f:
            json.dump({
                "collections": [],
                "known_books": [],
                "last_run": None,
                "version": "1.0"
            }, f, indent=2)
    print(f"✅ Book/Textbook/Report/Turing collector initialized")
    print(f"   Base: {BOOK_DIR}")
    print(f"   Sources: {', '.join(KNOWLEDGE_SOURCES.keys())}")
    print(f"   Subdirs: {sum(len(v['subdirs']) for v in KNOWLEDGE_SOURCES.values())} total")


def store_item(source_type, subdir, title, content_or_note="", url="",
               author="", year=0, extra=None):
    """Store a knowledge item into the corresponding directory"""
    info = KNOWLEDGE_SOURCES.get(source_type)
    if not info:
        print(f"❌ Unknown source type: {source_type}")
        return None

    base_dir = BOOK_DIR / info["dir"]
    sub_path = base_dir / subdir
    sub_path.mkdir(parents=True, exist_ok=True)

    # Generate unique ID
    item_id = hashlib.md5(f"{source_type}:{subdir}:{title}".encode()).hexdigest()[:12]
    safe_name = re.sub(r'[\\/:*?\"<>|]', '_', title)[:80]

    record = {
        "id": item_id,
        "type": source_type,
        "subdir": subdir,
        "title": title[:200],
        "author": author,
        "year": year,
        "url": url,
        "note": (content_or_note or "")[:2000],
        "collected_at": datetime.now().isoformat(),
    }
    if extra:
        record.update(extra)

    path = sub_path / f"{item_id}_{safe_name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    # Update collection log
    with open(COLLECT_LOG, "r") as f:
        log = json.load(f)
    existing_ids = {r["id"] for r in log["collections"]}
    if item_id not in existing_ids:
        log["collections"].append({
            "id": item_id, "type": source_type, "subdir": subdir,
            "title": title[:60], "path": str(path),
            "ts": datetime.now().isoformat(),
        })
        log["last_run"] = datetime.now().isoformat()
        if len(log["collections"]) > 2000:
            log["collections"] = log["collections"][-1000:]
        with open(COLLECT_LOG, "w") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
        print(f"  📥 [{source_type}/{subdir}] {title[:60]}")
    return path


def import_known_literature():
    """Import pre-defined known literature into storage"""
    count = 0
    for item in KNOWN_LITERATURE:
        path = store_item(
            source_type=item["type"],
            subdir=item["subdir"],
            title=item["title"],
            url=item["url"],
            author=item.get("source", ""),
            year=item.get("year", 0),
            extra={"note": item.get("note", "")}
        )
        if path:
            count += 1
    return count


def import_turing_classics():
    """Import Turing series book list into storage"""
    classics_dir = BOOK_DIR / "turing"
    count = 0
    for category, books in TURING_CLASSICS.items():
        for book in books:
            path = store_item(
                source_type="turing",
                subdir=category,
                title=book["title"],
                url=book.get("url", ""),
                author=book.get("author", ""),
                year=book.get("year", 0),
                extra={
                    "press": book.get("press", ""),
                    "isbn": book.get("isbn", ""),
                    "category_label": KNOWLEDGE_SOURCES["turing"]["subdirs"].get(category, category),
                    "source_type": "图灵系列"
                }
            )
            if path:
                count += 1
    return count


def search_by_keywords(source_type, subdir, keywords, limit=5):
    """
    Search for new items using the given keywords.
    This is a placeholder — actual search uses web_search tool externally.
    Returns the keywords that should be searched.
    """
    info = KNOWLEDGE_SOURCES.get(source_type)
    label = info["subdirs"].get(subdir, subdir) if info else subdir
    return {
        "type": source_type,
        "subdir": subdir,
        "label": label,
        "keywords": keywords,
        "suggested_limit": limit,
        "note": f"Use web_search or firecrawl_search with these keywords to find new {label}"
    }


def get_search_plan(priority_filter=None):
    """Get an ordered search plan for all enabled collection rules"""
    plan = []
    for source_type, subdirs in COLLECTION_RULES.items():
        for subdir, rules in subdirs.items():
            p = rules.get("priority", "P2")
            if priority_filter and p != priority_filter:
                continue
            plan.append(search_by_keywords(source_type, subdir, rules["keywords"]))
    return plan


def status():
    """Show collection status"""
    counts = {"total_items": 0, "by_type": {}, "by_subdir": {}}
    for source_type, info in KNOWLEDGE_SOURCES.items():
        base_dir = BOOK_DIR / info["dir"]
        type_count = 0
        for subdir_name in info["subdirs"]:
            sub_path = base_dir / subdir_name
            if sub_path.exists():
                n = len(list(sub_path.glob("*.json")))
                counts["by_subdir"][f"{source_type}/{subdir_name}"] = n
                type_count += n
        counts["by_type"][source_type] = type_count
        counts["total_items"] += type_count
    try:
        with open(COLLECT_LOG, "r") as f:
            log = json.load(f)
            counts["last_run"] = log.get("last_run", "never")
    except:
        counts["last_run"] = "never"
    return counts


def generate_routing_rules():
    """Generate agent routing rules for the new knowledge sources"""
    routes = {
        "_version": "1.0",
        "_source": "book_textbook_collector",
        "_updated": datetime.now().isoformat(),
        "routing": [
            # 教材 → 对应专业Agent
            {"source": "textbook/battery", "target_agents": ["伏安", "程实"],
             "reason": "电池/电化学教材"},
            {"source": "textbook/materials", "target_agents": ["伏安"],
             "reason": "材料科学教材"},
            {"source": "textbook/ai_ml", "target_agents": ["琢言", "算法", "绘影"],
             "reason": "AI/ML教材"},
            {"source": "textbook/programming", "target_agents": ["铸锋", "规尺"],
             "reason": "编程/算法教材"},
            {"source": "textbook/math", "target_agents": ["通量", "算渊"],
             "reason": "数学教材"},
            # 文献 → 对应Agent
            {"source": "literature/prelithiation_review", "target_agents": ["伏安"],
             "reason": "预锂化综述"},
            {"source": "literature/prelithiation_paper", "target_agents": ["伏安"],
             "reason": "预锂化研究论文"},
            {"source": "literature/anode_silicon", "target_agents": ["伏安", "程实"],
             "reason": "硅负极研究"},
            {"source": "literature/cathode_lco", "target_agents": ["伏安"],
             "reason": "正极补锂研究"},
            # 报告 → 多Agent交叉
            {"source": "report/industry", "target_agents": ["伏安", "程实", "运筹"],
             "reason": "行业研究报告"},
            {"source": "report/broker", "target_agents": ["伏安", "运筹"],
             "reason": "券商研报"},
            {"source": "report/whitepaper", "target_agents": ["伏安", "程实"],
             "reason": "企业白皮书"},
            # 图灵系列 → 对应技术Agent
            {"source": "turing/computer_science", "target_agents": ["算法", "归藏"],
             "reason": "计算机科学经典"},
            {"source": "turing/programming", "target_agents": ["铸锋", "规尺"],
             "reason": "程序设计经典"},
            {"source": "turing/ai_ml", "target_agents": ["琢言", "算法", "绘影"],
             "reason": "AI/ML经典"},
            {"source": "turing/math_stats", "target_agents": ["通量", "算渊"],
             "reason": "数学/统计经典"},
            {"source": "turing/electronics", "target_agents": ["构形", "程实"],
             "reason": "电子/电气工程"},
        ]
    }
    path = BOOK_DIR / "_routing.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(routes, f, ensure_ascii=False, indent=2)
    print(f"✅ Routing rules written to {path}")
    return path


# ===== 主入口 =====
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "init"

    if cmd == "init":
        init()
        # Import initial data
        n1 = import_known_literature()
        print(f"  Imported {n1} known literature items")
        n2 = import_turing_classics()
        print(f"  Imported {n2} Turing series books")
        generate_routing_rules()
        print(f"\n✅ Initial import complete: {n1} literature + {n2} Turing books")

    elif cmd == "status":
        s = status()
        print(f"Book/Textbook Knowledge Status:")
        print(f"  Total items: {s['total_items']}")
        print(f"  By type: {json.dumps(s['by_type'], ensure_ascii=False)}")
        print(f"  By subdir: {json.dumps(s['by_subdir'], ensure_ascii=False)}")
        print(f"  Last run: {s['last_run']}")
        print(f"  Location: {BOOK_DIR}")

    elif cmd == "import":
        n1 = import_known_literature()
        n2 = import_turing_classics()
        print(f"Imported: {n1} literature + {n2} Turing books")

    elif cmd == "search_plan":
        priority = sys.argv[2] if len(sys.argv) > 2 else None
        plan = get_search_plan(priority)
        print(f"Search Plan ({len(plan)} items):")
        for p in plan:
            print(f"  [{p['type']}/{p['subdir']}] {p['label']}")
            for kw in p['keywords']:
                print(f"    -> \"{kw}\"")

    elif cmd == "routing":
        generate_routing_rules()

    else:
        print("Commands: init, status, import, search_plan, routing")
