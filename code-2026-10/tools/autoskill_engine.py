#!/usr/bin/env python3
"""AutoSkill引擎 v2 — 从采集日志自动提炼skill候选 (对齐AutoSkill论文)
数据源: agent_knowledge/_collection_log.json (结构化研究记录)
输出: skill候选清单 + 已存在skill对比
"""
import json, os, datetime

LOG = r'D:\hermes\data\agent_knowledge\_collection_log.json'
OUT = r'D:\hermes\data\skill_candidates'
SKILLS_DIR = r'D:\hermes\hermes-data\profiles\mybot\skills'

# 已有skill映射 (topic → 已覆盖skill)
EXISTING_SKILLS = [
    'lsa-hi-sparse-attention', 'security-sandbox', 'material-characterization',
    'attention-compression', 'attention-kv-compression', 'network-resilience',
    'memory-consolidation-engine', 'self-improving-agent', 'agent-knowledge-routing',
    'hermes-memory-extension', 'token-compression-stack', 'skill-creator-and-finder',
]

def load_log():
    with open(LOG, encoding='utf-8') as f:
        return json.load(f).get('collections', [])

def topic_to_skill_candidate(entry):
    """采集条目 → skill候选"""
    name = entry.get('name', '')
    note = entry.get('note', '')
    level = entry.get('level', 'P2')
    
    # 判断是否已被skill覆盖
    covered_by = None
    for sk in EXISTING_SKILLS:
        if sk in name or sk.split('-')[0] in name:
            covered_by = sk
            break
    
    # 生成skill名
    skill_name = 'skill-' + name.lower().replace('_', '-').replace(' ', '-')
    
    return {
        'candidate_name': skill_name,
        'source': name,
        'level': level,
        'already_covered': covered_by,
        'note_preview': note[:120],
        'action': '已覆盖' if covered_by else '待创建',
        'detected_at': datetime.datetime.now().isoformat()
    }

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    print("=== AutoSkill v2: 采集日志→skill候选 ===\n")
    
    entries = load_log()
    candidates = []
    for e in entries:
        c = topic_to_skill_candidate(e)
        candidates.append(c)
    
    # 待创建清单
    to_create = [c for c in candidates if c['action'] == '待创建']
    covered = [c for c in candidates if c['action'] == '已覆盖']
    
    print(f"总采集: {len(candidates)} | 已覆盖: {len(covered)} | 待创建: {len(to_create)}\n")
    print("=== 待创建候选 ===")
    for c in to_create:
        print(f"  [P{c['level']}] {c['source']}: {c['note_preview'][:60]}")
    print(f"\n=== 已覆盖 ({len(covered)}) ===")
    for c in covered:
        print(f"  ✅ {c['source']} → {c['already_covered']}")
    
    # 保存
    with open(os.path.join(OUT, 'candidates.json'), 'w', encoding='utf-8') as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 候选已保存: {OUT}/candidates.json")
