"""
巡天 - Agent集群知识补给系统
为25个专业Agent定向搜集公开信息和技术资源
"""
import json, os, re, hashlib
from pathlib import Path
from datetime import datetime

KNOWLEDGE_ROOT = Path("D:/hermes/data/agent_knowledge")
COLLECT_LOG = KNOWLEDGE_ROOT / "_collection_log.json"

AGENTS = {
    "巡天": {"domain": "AI/ML", "keywords": ["OSINT","threat intelligence","reconnaissance","information gathering"]},
    "铸锋": {"domain": "工程", "keywords": ["code generation","IDE plugin","language server","framework update"]},
    "明鉴": {"domain": "数据", "keywords": ["data analysis","visualization","BI tool","analytics library"]},
    "绘影": {"domain": "AI/ML", "keywords": ["image generation","diffusion model","computer vision","3D rendering"]},
    "琢言": {"domain": "AI/ML", "keywords": ["LLM","NLP","language model","benchmark","evaluation"]},
    "规尺": {"domain": "工程", "keywords": ["testing framework","CI/CD","code quality","linting"]},
    "伏安": {"domain": "专业", "keywords": ["battery","electrochemistry","lithium","energy storage","DSC"]},
    "程实": {"domain": "工程", "keywords": ["manufacturing process","calendering","roll press","process engineering"]},
    "御界": {"domain": "安全", "keywords": ["security","vulnerability","defense","zero trust"]},
    "析微": {"domain": "专业", "keywords": ["computer vision","defect detection","OCR","image analysis"]},
    "构形": {"domain": "工程", "keywords": ["CAD","3D modeling","FEA","GD&T","DFM"]},
    "听澜": {"domain": "专业", "keywords": ["speech recognition","audio processing","voiceprint","TTS"]},
    "社保": {"domain": "专业", "keywords": ["social security","insurance","policy","benefits"]},
    "通量": {"domain": "数据", "keywords": ["mathematical modeling","simulation","numerical methods","optimization"]},
    "算渊": {"domain": "数据", "keywords": ["algorithm","complexity","data structure","competitive programming"]},
    "归藏": {"domain": "数据", "keywords": ["knowledge graph","entity recognition","ontology","RDF"]},
    "证道": {"domain": "专业", "keywords": ["formal verification","theorem proving","Lean","Coq","SAT/SMT"]},
    "铸盾": {"domain": "安全", "keywords": ["fuzzing","SAST","DAST","vulnerability discovery"]},
    "破阵": {"domain": "安全", "keywords": ["penetration testing","red team","exploit","C2 framework"]},
    "守序": {"domain": "安全", "keywords": ["code review","security audit","static analysis","best practices"]},
    "调度": {"domain": "工程", "keywords": ["task scheduling","resource management","workflow engine","load balancing"]},
    "通联": {"domain": "工程", "keywords": ["API gateway","message queue","protocol","webhook"]},
    "审微": {"domain": "数据", "keywords": ["audit logging","monitoring","observability","alerting"]},
    "运筹": {"domain": "专业", "keywords": ["project management","agile","kanban","productivity"]},
    "算法": {"domain": "AI/ML", "keywords": ["MLOps","model serving","AI architecture","research frontier"]},
}

def init():
    """Initialize agent knowledge directories"""
    for agent_name, info in AGENTS.items():
        agent_dir = KNOWLEDGE_ROOT / agent_name
        agent_dir.mkdir(parents=True, exist_ok=True)
    # Create domain dirs
    for domain in set(a["domain"] for a in AGENTS.values()):
        (KNOWLEDGE_ROOT / "_domains" / domain).mkdir(parents=True, exist_ok=True)
    # Init log
    if not COLLECT_LOG.exists():
        with open(COLLECT_LOG, "w") as f:
            json.dump({"collections": [], "last_run": None, "by_agent": {}}, f, indent=2)
    print(f"✅ Agent knowledge system initialized")
    print(f"   Agents: {len(AGENTS)}")
    print(f"   Domains: {len(set(a['domain'] for a in AGENTS.values()))}")
    print(f"   Storage: {KNOWLEDGE_ROOT}")

def store(agent_name, item_type, title, content, source_url=""):
    """Store collected knowledge item for an agent"""
    agent_dir = KNOWLEDGE_ROOT / agent_name
    agent_dir.mkdir(parents=True, exist_ok=True)
    
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', title)[:80]
    item_id = hashlib.md5(f"{agent_name}{title}".encode()).hexdigest()[:12]
    
    record = {
        "id": item_id,
        "agent": agent_name,
        "type": item_type,
        "title": title[:200],
        "content": content[:2000],
        "source": source_url,
        "collected_at": datetime.now().isoformat(),
    }
    
    path = agent_dir / f"{item_id}_{safe_name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    
    # Update log
    with open(COLLECT_LOG, "r") as f:
        log = json.load(f)
    if agent_name not in log["by_agent"]:
        log["by_agent"][agent_name] = 0
    log["by_agent"][agent_name] += 1
    log["collections"].append({"id": item_id, "agent": agent_name, "title": title[:60], "ts": datetime.now().isoformat()})
    log["last_run"] = datetime.now().isoformat()
    # Keep log manageable
    if len(log["collections"]) > 1000:
        log["collections"] = log["collections"][-500:]
    with open(COLLECT_LOG, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    
    return path

def status():
    """Show collection status"""
    with open(COLLECT_LOG, "r") as f:
        log = json.load(f)
    return {
        "total_items": sum(log["by_agent"].values()),
        "by_agent": log["by_agent"],
        "last_run": log["last_run"],
    }

def search_by_domain(domain):
    """Find all items for a domain"""
    results = []
    for agent_name, info in AGENTS.items():
        if info["domain"] == domain:
            agent_dir = KNOWLEDGE_ROOT / agent_name
            if agent_dir.exists():
                for f in agent_dir.glob("*.json"):
                    if f.name != "_collection_log.json":
                        try:
                            with open(f) as fh:
                                data = json.load(fh)
                            results.append(data)
                        except: pass
    return results

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "init":
        init()
    elif cmd == "status":
        s = status()
        print(f"Agent Knowledge: {json.dumps(s, ensure_ascii=False, indent=2)}")
    elif cmd == "domain":
        d = sys.argv[2] if len(sys.argv) > 2 else "AI/ML"
        items = search_by_domain(d)
        print(f"Domain {d}: {len(items)} items")
