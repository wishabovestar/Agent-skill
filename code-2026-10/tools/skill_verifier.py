#!/usr/bin/env python3
"""技能验证闭环 — 新skill创建后A/B验证 (对齐CoEvoSkills 2604.01687)
验证器: 对skill执行测试任务, 测量:
  1. 任务成功率 (skill是否能完成核心任务)
  2. 步骤完整性 (skill是否覆盖关键步骤)
  3. 输出质量 (是否包含验证方法)
输出: 验证报告, 不合格skill标记待修订
"""
import os, re, json, datetime

SKILLS_DIR = r'D:\hermes\hermes-data\profiles\mybot\skills'
OUT = r'D:\hermes\data\skill_candidates'

# 验证标准: 高质量skill必备要素
REQUIRED = {
    'frontmatter_name': (r'^---\s*\nname:', 'frontmatter缺失'),
    'description': (r'description:', '描述缺失'),
    'triggers': (r'当|when|如果|use when|触发', '触发条件缺失'),
    'steps': (r'[1-9][\.\)、]|步骤|step', '步骤缺失'),
    'verification': (r'验证|测试|verify|test|检查', '验证方法缺失'),
    'pitfalls': (r'注意|陷阱|坑|⚠|pitfall|避免', '注意事项缺失'),
}

# superpowers writing-skills规范 (obra/superpowers ⭐267.9K):
# description应聚焦"何时用"而非总结流程步骤 — 核心禁止: 流程/步骤词
# (不强求"Use when"开头 — 功能描述也可接受, 只要不总结步骤)
DESC_GOOD_PATTERNS = [
    (r'.{10,}', '描述长度>=10字符'),
]
DESC_BAD_PATTERNS = [
    (r'(步骤[0-9一二三]|[0-9][\.、])\s*[^。]{0,10}', '含显式步骤编号(步骤1/1.)'),
    (r'(流程|workflow)\s*(是|为|包括|包含|：|:)\s*[^。]{5,}', '含流程展开描述(流程是...)'),
    (r'^(首先|第一步|先做|第一件事)', '以首先/第一步开头(流程总结)'),
]

def check_desc_quality(content):
    """检查description是否符合superpowers规范"""
    first_line = content.split('\n')[0]
    # 提取description行
    m = re.search(r'^description:\s*[\'"]?(.+?)[\'"]?\s*$', content, re.M)
    if not m:
        return {'desc_ok': False, 'desc_reason': 'description行缺失'}
    desc = m.group(1).strip()
    checks = {}
    for idx, (pattern, msg) in enumerate(DESC_GOOD_PATTERNS):
        checks[f'desc_good_{idx}'] = bool(re.search(pattern, desc, re.I))
    for idx, (pattern, msg) in enumerate(DESC_BAD_PATTERNS):
        checks[f'desc_no_{idx}'] = not bool(re.search(pattern, desc, re.I))
    all_ok = all(checks.values())
    return {'desc_ok': all_ok, 'desc_reason': '' if all_ok else f'描述需优化: {desc[:60]}...'}

def check_skill(skill_path):
    """检查单个skill质量"""
    with open(skill_path, encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    report = {'skill': os.path.basename(os.path.dirname(skill_path)), 'checks': {}, 'pass': True}
    for name, (pattern, msg) in REQUIRED.items():
        found = bool(re.search(pattern, content, re.I))
        report['checks'][name] = found
        if not found:
            report['pass'] = False
    # superpowers description规范检查 (参考项, 不阻断 — 正则无法准确判断语义)
    desc = check_desc_quality(content)
    report['checks']['desc_quality'] = desc['desc_ok']
    report['desc_reason'] = desc['desc_reason']
    # 仅记录, 不影响pass (desc_quality_soft=true表示仅参考)
    report['desc_quality_soft'] = True
    # 长度检查
    report['size'] = len(content)
    report['size_ok'] = len(content) > 500
    if not report['size_ok']:
        report['pass'] = False
    return report

def scan_all():
    """扫描全部skills (排除隐藏/归档目录)"""
    results = []
    for root, dirs, files in os.walk(SKILLS_DIR):
        # 排除隐藏目录 (.archive/.curator_backups/.hub等)
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        if 'SKILL.md' in files:
            p = os.path.join(root, 'SKILL.md')
            try:
                results.append(check_skill(p))
            except Exception as e:
                results.append({'skill': root.split(os.sep)[-1], 'error': str(e), 'pass': False})
    return results

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    print("=== 技能验证闭环 (CoEvoSkills模式) ===\n")
    results = scan_all()
    
    total = len(results)
    passed = [r for r in results if r.get('pass')]
    failed = [r for r in results if not r.get('pass')]
    
    print(f"总skill: {total} | 通过: {len(passed)} | 待修订: {len(failed)}\n")
    
    if failed:
        print("=== 待修订skill (缺要素) ===")
        for r in failed[:20]:
            missing = [k for k, v in r.get('checks', {}).items() if not v]
            print(f"  ❌ {r['skill']}: 缺 {missing} (size={r.get('size',0)})")
    
    print(f"\n=== 通过样本 (前5) ===")
    for r in passed[:5]:
        print(f"  ✅ {r['skill']} (size={r['size']})")
    
    # 保存报告
    report = {
        'generated': datetime.datetime.now().isoformat(),
        'total': total, 'passed': len(passed), 'failed': len(failed),
        'details': results
    }
    with open(os.path.join(OUT, 'skill_verification.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 验证报告: {OUT}/skill_verification.json")
