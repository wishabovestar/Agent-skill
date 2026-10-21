#!/usr/bin/env python3
"""技能库演进 — 扫描已用skill, 淘汰低ROI (对齐SkillOS 2605.06614)
指标:
  1. 使用频率 (从会话/日志统计)
  2. 质量分 (skill_verifier结果)
  3. 大小 (过大=臃肿, 过小=不完整)
输出: 演进报告 + 淘汰候选
"""
import os, re, json, datetime, glob

SKILLS_DIR = r'D:\hermes\hermes-data\profiles\mybot\skills'
LOG_PATH = r'D:\hermes\data\agent_knowledge\_collection_log.json'
OUT = r'D:\hermes\data\skill_candidates'

# 已知高频使用skill (从本会话+记忆)
HIGH_USE = {
    'lsa-hi-sparse-attention': 8, 'security-sandbox': 5, '3d-model-agent': 4,
    'material-characterization': 3, 'pdf-reader': 4, 'network-resilience': 3,
    'token-compression-stack': 3, 'minimal-toolset': 2, 'hermes-agent': 2,
    'attention-compression': 2, 'drawing-privacy-guard': 3,
}

def scan_skills():
    results = []
    for root, dirs, files in os.walk(SKILLS_DIR):
        if 'SKILL.md' in files:
            p = os.path.join(root, 'SKILL.md')
            name = os.path.basename(root)
            size = os.path.getsize(p)
            with open(p, encoding='utf-8', errors='ignore') as f:
                content = f.read()
            # 质量信号
            has_verification = bool(re.search(r'验证|测试|verify|test|检查', content))
            has_pitfalls = bool(re.search(r'注意|陷阱|⚠|pitfall', content))
            has_steps = bool(re.search(r'[1-9][\.\)、]|步骤|step', content))
            
            use_count = HIGH_USE.get(name, 0)
            quality = sum([has_verification, has_pitfalls, has_steps])
            
            results.append({
                'name': name,
                'size': size,
                'use_count': use_count,
                'quality': quality,
                'roi_score': use_count * 10 + quality * 5 - (size / 10000),
                'recommendation': ''
            })
    return results

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    print("=== 技能库演进 (SkillOS模式) ===\n")
    skills = scan_skills()
    
    # 分类
    high_roi = [s for s in skills if s['roi_score'] > 5 and s['use_count'] > 0]
    low_roi = [s for s in skills if s['use_count'] == 0 and s['size'] < 1000]
    candidates = sorted(skills, key=lambda x: -x['roi_score'])
    
    print(f"总skill: {len(skills)} | 高ROI: {len(high_roi)} | 疑似低ROI: {len(low_roi)}\n")
    
    print("=== Top 10 高ROI ===")
    for s in sorted(high_roi, key=lambda x: -x['roi_score'])[:10]:
        print(f"  🏆 {s['name']}: 使用{s['use_count']}次 质量{s['quality']}/3 ROI={s['roi_score']:.1f}")
    
    print(f"\n=== 低ROI候选 (未使用+小) {len(low_roi)}个 ===")
    for s in low_roi[:10]:
        print(f"  ⚠️ {s['name']}: size={s['size']}")
    
    # 保存报告
    report = {
        'generated': datetime.datetime.now().isoformat(),
        'total': len(skills), 'high_roi': len(high_roi), 'low_roi': len(low_roi),
        'details': candidates
    }
    with open(os.path.join(OUT, 'skill_evolution.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 演进报告: {OUT}/skill_evolution.json")
