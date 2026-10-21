"""
巡天 - 算法知识采集器
为12种算法+DL/NN提供论文搜索和知识存储
关联数学组Agent: 算渊/通量/算法/明鉴/调度/归藏
"""
import json, urllib.request, urllib.parse, re
from pathlib import Path
from datetime import datetime

KNOWLEDGE_DIR = Path("D:/hermes/data/agent_knowledge/算法")
KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
COLLECT_LOG = KNOWLEDGE_DIR / "_collection_log.json"
ARXIV_URL = "http://export.arxiv.org/api/query"

ALGORITHMS = [
    {"name": "simulated_annealing", "cn": "退火算法", "arxiv": "simulated+annealing+optimization", "agent": "算渊"},
    {"name": "genetic_algorithm", "cn": "遗传算法", "arxiv": "genetic+algorithm+optimization", "agent": "算渊"},
    {"name": "random_forest", "cn": "随机森林", "arxiv": "random+forest+classification", "agent": "明鉴"},
    {"name": "convolutional_neural_network", "cn": "卷积神经网络", "arxiv": "convolutional+neural+network", "agent": "绘影"},
    {"name": "waterfall_algorithm", "cn": "瀑布算法", "arxiv": "waterfall+algorithm+optimization", "agent": "算渊"},
    {"name": "greedy_algorithm", "cn": "贪心算法", "arxiv": "greedy+algorithm+scheduling", "agent": "调度"},
    {"name": "knowledge_graph", "cn": "实体关系图", "arxiv": "knowledge+graph+embedding", "agent": "归藏"},
    {"name": "dijkstra", "cn": "迪克斯特拉", "arxiv": "dijkstra+shortest+path", "agent": "调度"},
    {"name": "particle_swarm", "cn": "粒子群优化", "arxiv": "particle+swarm+optimization", "agent": "算渊"},
    {"name": "spiral_algorithm", "cn": "螺旋算法", "arxiv": "spiral+optimization+algorithm", "agent": "算渊"},
    {"name": "tabu_search", "cn": "禁忌搜索", "arxiv": "tabu+search+combinatorial", "agent": "破阵"},
    {"name": "swarm_intelligence", "cn": "群体智能", "arxiv": "swarm+intelligence+optimization", "agent": "调度"},
    {"name": "deep_learning", "cn": "深度学习", "arxiv": "deep+learning+survey", "agent": "算法"},
    {"name": "neural_network", "cn": "神经网络", "arxiv": "neural+network+architecture", "agent": "算法"},
    {"name": "classical_statistics", "cn": "经典统计学", "arxiv": "classical+statistics+inference", "agent": "通量"},
    {"name": "bayesian_theorem", "cn": "贝叶斯定理", "arxiv": "bayesian+inference+probability", "agent": "通量"},
    {"name": "probability_theory", "cn": "概率论与数理统计", "arxiv": "probability+theory+mathematical+statistics", "agent": "通量"},
    {"name": "mathematical_analysis", "cn": "数学分析", "arxiv": "mathematical+analysis+calculus", "agent": "算渊"},
    {"name": "iterative_algorithm", "cn": "迭代算法", "arxiv": "iterative+algorithm+convergence", "agent": "算渊"},
    {"name": "fourier_transform", "cn": "傅立叶变换", "arxiv": "fourier+transform+signal+processing", "agent": "通量"},
    {"name": "convex_optimization", "cn": "凸优化", "arxiv": "convex+optimization+theory", "agent": "算渊"},
    {"name": "complex_analysis", "cn": "复分析", "arxiv": "complex+analysis+function+theory", "agent": "算渊"},
    {"name": "functional_analysis", "cn": "泛函分析", "arxiv": "functional+analysis+banach+hilbert", "agent": "算渊"},
]


def search_arxiv(query, max_results=3):
    """Search arXiv for papers"""
    params = urllib.parse.urlencode({
        'search_query': f'all:{query}',
        'sortBy': 'submittedDate',
        'sortOrder': 'descending',
        'max_results': max_results,
    })
    url = f"{ARXIV_URL}?{params}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Hermes/1.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml = resp.read().decode('utf-8')
            titles = re.findall(r'<title>(.*?)</title>', xml, re.DOTALL)
            ids = re.findall(r'<id>(.*?)</id>', xml)
            # Skip first title (it's the query title)
            results = []
            for i in range(1, min(len(titles), len(ids))):
                results.append({
                    "title": titles[i].strip()[:100],
                    "url": ids[i].strip(),
                    "query": query,
                })
            return results
    except Exception as e:
        return [{"error": str(e)[:60]}]

def store_results(algo, papers):
    """Store paper results"""
    record = {
        "algorithm": algo["cn"],
        "arxiv_query": algo["arxiv"],
        "agent": algo["agent"],
        "papers": papers,
        "collected_at": datetime.now().isoformat(),
    }
    # Save per-algorithm file
    path = KNOWLEDGE_DIR / f"{algo['name']}.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    
    # Update collection log
    log = []
    if COLLECT_LOG.exists():
        with open(COLLECT_LOG, 'r') as f:
            log = json.load(f)
    log.append({"algo": algo["cn"], "papers": len(papers), "ts": datetime.now().isoformat()})
    if len(log) > 100: log = log[-100:]
    with open(COLLECT_LOG, 'w') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    
    return path

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "collect"
    
    if cmd == "collect":
        print(f"📚 算法知识采集 — {len(ALGORITHMS)} 个主题")
        total_papers = 0
        for algo in ALGORITHMS:
            print(f"\n  🔍 [{algo['cn']}] → {algo['agent']}Agent")
            papers = search_arxiv(algo["arxiv"])
            path = store_results(algo, papers)
            if "error" not in papers[0]:
                for p in papers[:3]:
                    print(f"     📄 {p['title'][:60]}")
                total_papers += len(papers)
            else:
                print(f"     ❌ {papers[0]['error']}")
        
        print(f"\n✅ 采集完成: {total_papers} 篇论文")
        print(f"   存储: {KNOWLEDGE_DIR}")
        
        # Agent mapping summary
        agents = {}
        for algo in ALGORITHMS:
            a = algo["agent"]
            if a not in agents: agents[a] = []
            agents[a].append(algo["cn"])
        print(f"\n📊 Agent-算法映射:")
        for a, algos in sorted(agents.items()):
            print(f"  {a}: {', '.join(algos)}")
    
    elif cmd == "status":
        log = []
        if COLLECT_LOG.exists():
            with open(COLLECT_LOG, 'r') as f:
                log = json.load(f)
        files = list(KNOWLEDGE_DIR.glob("*.json"))
        print(f"算法知识库: {KNOWLEDGE_DIR}")
        print(f"JSON文件数: {len(files)}")
        print(f"采集次数: {len(log)}")
        if log:
            print(f"最后采集: {log[-1]['ts'][:16]}")
