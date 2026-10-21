#!/usr/bin/env python3
"""MemSkill模式 — 记忆操作可学习进化 (对齐MemSkill论文 2602.02474)
核心: 记忆操作(提取/巩固/修剪/压缩)本身不是静态规则, 而是可学习的技能
实现: 
  1. 记忆质量评分 (提取有用性)
  2. 记忆巩固策略选择 (根据使用频率自动调整)
  3. 记忆修剪规则进化 (淘汰低价值)
  4. 反馈闭环: 记忆被使用→强化, 未使用→衰减
"""
import json, os, datetime, time

MEM_FILE = r'D:\hermes\data\credentials\memory_skills_state.json'

def load_state():
    if os.path.exists(MEM_FILE):
        with open(MEM_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {'entries': {}, 'skills': {}, 'created': datetime.datetime.now().isoformat()}

def save_state(state):
    with open(MEM_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def register_entry(state, key, content, importance='medium'):
    """注册记忆条目 (模拟MEMORY.md条目)"""
    now = datetime.datetime.now().isoformat()
    state['entries'][key] = {
        'content': content,
        'importance': importance,
        'created': now,
        'last_used': None,
        'use_count': 0,
        'score': 0.5
    }

def use_entry(state, key):
    """记忆被使用 → 强化 (MemSkill: 使用反馈闭环)"""
    if key in state['entries']:
        e = state['entries'][key]
        e['use_count'] += 1
        e['last_used'] = datetime.datetime.now().isoformat()
        # 学习率: 使用次数越多, 强化越快 (对数增长)
        e['score'] = min(1.0, e['score'] + 0.1 * (1 + e['use_count'] * 0.05))
        return e['score']
    return None

def consolidate(state, key, new_info):
    """记忆巩固: 将新信息合并进已有条目 (海马体巩固类比)"""
    if key in state['entries']:
        e = state['entries'][key]
        e['content'] += f" | 巩固: {new_info}"
        e['consolidations'] = e.get('consolidations', 0) + 1
        return True
    return False

def prune(state, threshold=0.3, max_age_days=90):
    """记忆修剪进化: 淘汰低分/过旧条目 (突触修剪类比)"""
    now = time.time()
    pruned = []
    for key in list(state['entries'].keys()):
        e = state['entries'][key]
        # 时间衰减
        if e['last_used']:
            last = datetime.datetime.fromisoformat(e['last_used']).timestamp()
            age_days = (now - last) / 86400
            decay = 0.5 ** (age_days / 30)  # 30天半衰期
        else:
            decay = 0.3
        e['score'] *= decay
        if e['score'] < threshold:
            pruned.append(key)
            del state['entries'][key]
    return pruned

def learn_strategy(state, feedback):
    """学习记忆策略: 根据反馈调整 (MemSkill核心)
    feedback: {'entry': key, 'useful': bool, 'task_type': str}
    """
    key = feedback['entry']
    if key not in state['entries']:
        return
    useful = feedback['useful']
    task = feedback.get('task_type', 'general')
    
    # 策略表: 不同任务类型→不同强化系数
    if 'strategy' not in state['skills']:
        state['skills']['strategy'] = {'default': 0.1}
    strat = state['skills']['strategy']
    coef = strat.get(task, strat['default'])
    
    e = state['entries'][key]
    e['score'] += coef if useful else -coef * 2  # 惩罚更重
    e['score'] = max(0, min(1, e['score']))
    # 更新策略 (元学习: 该任务类型下此条目的贡献)
    strat[task] = coef * 1.1 if useful else coef * 0.9
    return e['score']

if __name__ == '__main__':
    print("=== MemSkill: 记忆操作可学习进化 ===\n")
    state = load_state()
    
    # 测试流程
    register_entry(state, 'lsa_hi', 'LSA-HI: per-block qb=512 cos=0.74', 'high')
    register_entry(state, 'cadquery', 'CadQuery 2.8 纽扣电池STEP成功', 'medium')
    register_entry(state, 'vps_sentinel', 'VPS哨兵cron每10分钟', 'medium')
    
    print("注册3条记忆:")
    for k, e in state['entries'].items():
        print(f"  {k}: score={e['score']:.2f}")
    
    # 使用反馈
    print("\n使用'lsa_hi'记忆(2次)+学习反馈:")
    s1 = use_entry(state, 'lsa_hi')
    s2 = use_entry(state, 'lsa_hi')
    s3 = learn_strategy(state, {'entry': 'lsa_hi', 'useful': True, 'task_type': 'attention_optim'})
    print(f"  使用后: score={s2:.2f} → 策略学习后={s3:.2f}")
    
    # 巩固
    print("\n巩固'vps_sentinel'(加入新信息):")
    consolidate(state, 'vps_sentinel', '新增Telegram通知通道')
    print(f"  巩固次数: {state['entries']['vps_sentinel'].get('consolidations', 0)}")
    
    # 修剪 (模拟老记忆)
    register_entry(state, 'old_task', '2025年旧任务记录', 'low')
    state['entries']['old_task']['last_used'] = (datetime.datetime.now() - datetime.timedelta(days=120)).isoformat()
    pruned = prune(state, threshold=0.2, max_age_days=90)
    print(f"\n修剪: 移除 {len(pruned)} 条: {pruned}")
    
    save_state(state)
    print(f"\n✅ MemSkill状态已保存: {MEM_FILE}")
    print(f"  剩余条目: {len(state['entries'])} | 策略: {state['skills']}")
