#!/usr/bin/env python3
"""批量获取arXiv论文摘要 (12篇技能进化领域)
用法: python fetch_papers.py
"""
import urllib.request, json, re, time

PAPERS = [
    ('2505.03335', 'Absolute Zero'),
    ('2602.21320', 'Tool-R0'),
    ('2511.16043', 'Agent0'),
    ('2511.10395', 'AgentEvolver'),
    ('2605.06614', 'SkillOS'),
    ('2602.08234', 'SkillRL'),
    ('2512.17102', 'SAGE'),
    ('2510.16079', 'EvolveR'),
    ('2604.01687', 'CoEvoSkills'),
    ('2602.02474', 'MemSkill'),
    ('2603.02766', 'EvoSkill'),
    ('2603.01145', 'AutoSkill'),
]

def fetch_arxiv(paper_id):
    """通过arXiv API获取元数据"""
    url = f"http://export.arxiv.org/api/query?id_list={paper_id}&max_results=1"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode('utf-8', errors='replace')
        # 提取entry内title (第一个<title>是查询回显)
        entries = re.findall(r'<entry>(.*?)</entry>', data, re.S)
        entry = entries[0] if entries else data
        t = re.search(r'<title>(.*?)</title>', entry, re.S)
        title = t.group(1).strip() if t else 'N/A'
        s = re.search(r'<summary>(.*?)</summary>', entry, re.S)
        summary = s.group(1).strip() if s else 'N/A'
        a = re.findall(r'<name>(.*?)</name>', entry)
        return {'id': paper_id, 'title': title, 'summary': summary[:500], 'authors': a[:5]}
    except Exception as e:
        return {'id': paper_id, 'title': 'ERROR', 'summary': str(e), 'authors': []}

if __name__ == '__main__':
    results = []
    for pid, name in PAPERS:
        print(f"获取 {name} ({pid})...")
        r = fetch_arxiv(pid)
        r['short_name'] = name
        results.append(r)
        time.sleep(1)  # arXiv限速
    
    with open(r'D:/hermes/data/results/skill_evolution_papers.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 已保存 {len(results)} 篇论文")
    for r in results:
        print(f"  {r['short_name']}: {r['title'][:60]}")
